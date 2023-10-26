#!/usr/bin/env python3
import asyncio
from collections import defaultdict

import telethon.utils
# Imports Telethon
from telethon import events, functions
from telethon.tl import types
from telethon.tl.custom import Button
from telethon.tl.types import InputMessageID
from telethon.utils import get_peer_id, resolve_id

from clients import client, queue, user_clients
from commands import handle_regular_commands
from download_worker import download_worker
from env import *
from logger import logger
from model.subscription import Subscription
from utils import send_folders_structure, \
    execute_queries, tg_send_message, is_file_torrent, splash, replace_right

download_path_torrent = TG_DOWNLOAD_PATH_TORRENTS  # Directory where to save torrent file (if enabled). Connect with
# torrent client to start download.
number_of_parallel_downloads = TG_MAX_PARALLEL
current_messages = list()
current_timer = None
timeout = 1
subs_query = execute_queries([('SELECT user_id, chat_id, location, display_name FROM subscriptions', ())])[0]
subs = defaultdict(dict)
for x in list(subs_query):
    subs[int(x[0])][int(x[1])] = Subscription(int(x[0]), int(x[1]), x[2], x[3])


async def put_in_queue(final_path: str, messages_id: str):
    message_id, event_id = messages_id.split(';')
    result = await client(
        functions.messages.GetMessagesRequest(id=[InputMessageID(int(message_id)), InputMessageID(int(event_id))]))
    message = result.messages[0]
    event = result.messages[1]
    await queue.put([event, message, final_path, False, None])


@client.on(events.CallbackQuery())
async def callback(event):
    message_id = event.data.decode('utf-8')
    if message_id.startswith('CANCEL,'):
        execute_queries([(f'DELETE FROM locations', ())])
        return await event.edit('Canceled')
    elif message_id.startswith('STOP,'):
        message_id = message_id.split(',')[1]
        media_id, final_path, messages, is_subscription = \
            execute_queries([(f'SELECT message_id, location, messages_ids, is_subscription FROM locations WHERE id=?',
                              (message_id,)), (f'DELETE FROM locations', ())])[0][0]
        if is_subscription != 1:
            producers = list(map(lambda x: asyncio.create_task(put_in_queue(final_path, x)), messages.split(',')))
            await asyncio.gather(*producers)
        else:
            title = replace_right(messages, f',{media_id}', '', 1)
            user_id, chat_id = media_id.split(',')
            saved = execute_queries([(
                'INSERT INTO subscriptions(user_id, chat_id, location, display_name) VALUES (?, ?, ?, ?)',
                (user_id, chat_id, final_path, title))])[0]
            if saved is True:
                subs[int(user_id)][int(chat_id)] = Subscription(int(user_id), int(chat_id), final_path, title)
                await event.edit('🎉 Subscription created, I will download new files from this chat'
                                 f' when a new media is sent inside <i>"{final_path}"</pre>')
            else:
                await event.edit('❗ Error saving chat id, try again')
    elif message_id.startswith('NEW,'):
        message_id = message_id.split(',')[1]
        await event.edit('Insert new folder name',
                         buttons=[[Button.inline('Back ', f'{message_id}'), Button.inline('❌ Cancel', data='CANCEL')]])
    else:
        is_back = False
        if message_id.startswith('BACK,'):
            message_id = message_id.split(',')[1]
            is_back = True
        media_id, base_path, messages_ids, is_subscription = \
            execute_queries(
                [(f'SELECT message_id, location, messages_ids, is_subscription FROM locations WHERE id=?',
                  (message_id,)),
                 (f'DELETE FROM locations', ())])[0][0]
        if is_back:
            base_path = os.path.split(base_path)[0]
        if is_subscription == 1:
            title = replace_right(messages_ids, f',{media_id}', '', 1)
            messages_ids = [title, media_id]
        else:
            messages_ids = messages_ids.split(',')

        await send_folders_structure(event, messages_ids, base_path, is_subscription=is_subscription == 1)


async def answer_with_structure(message):
    messages_id = current_messages.copy()
    current_messages.clear()
    await send_folders_structure(message, messages_id)


@events.register(events.NewMessage(func=lambda e: e.is_channel is True or e.is_group is True))
async def user_event_handler(event):
    real_id = get_peer_id(event.chat_id)
    chat_id, peer_type = resolve_id(real_id)
    if event.message.media is None:
        return

    u_clients = user_clients.values()
    message_client = event.client
    u_client = next((cli for cli in u_clients if cli.get_client() == message_client), None)
    if u_client and u_client.get_user_id() in subs and chat_id in subs[u_client.get_user_id()]:
        subscription = subs[u_client.get_user_id()][chat_id]
        event.message.peer_id = u_client.get_user_id()
        update = events.NewMessage.Event(event.message)
        await handler(update, is_subscription=True, subscription=subscription, user_client=u_client)


@client.on(events.Raw(types=types.UpdateNewMessage, func=lambda e: e.message.action and (
        e.message.action.button_id == REQUEST_CHAT_ID or e.message.action.button_id == REQUEST_CHAT_ID + 1)))
async def raw_handler(event):
    real_id = get_peer_id(event.message.action.peer)
    chat_id, peer_type = resolve_id(real_id)
    real_user_id = get_peer_id(event.message.peer_id)
    user_id, _ = resolve_id(real_user_id)
    if user_id in subs and chat_id in subs[user_id]:
        await client.send_message(user_id, '❌ Already subscribed')
    else:
        user_client = user_clients[user_id]
        if user_client.is_authenticated() is False:
            await client.send_message(user_id,
                                      '⚠️ You are not authenticated. Please use /login command to authenticate')
        else:
            chat_from = await user_client.get_client().get_entity(event.message.action.peer)
            message = await client.send_message(event.message.peer_id, '📂 Choose download folder')
            await send_folders_structure(message, [chat_from.title, f'{user_id},{chat_id}'], is_subscription=True)


@events.register(events.NewMessage)
async def handler(update: events.NewMessage.Event, is_subscription=False, subscription: Subscription = None,
                  user_client=None):
    try:
        real_id = get_peer_id(update.message.peer_id)
        CID, peer_type = resolve_id(real_id)

        if (update.message.contact and (AUTHORIZED_USER and CID in user_ids) and CID in user_clients
                and user_clients[CID].is_authenticated() is not True
                and update.message.contact.user_id == CID):
            phone = telethon.utils.parse_phone(update.message.contact.phone_number)
            await user_clients[CID].get_client().send_code_request(phone, force_sms=False)
            user_clients[CID].set_phone(phone)
            await client.send_message(CID, '📱 Insert code received via Telegram with the format <b>+[code]</b>\n'
                                           'and put whitespaces between the digits\n\n'
                                           'Example: <b>+ 2 3 4 6 2</b>',
                                      buttons=Button.clear())
            return

        if update.message.from_id is not None:
            logger.info(
                "USER ON GROUP => U:[%s]G:[%s]M:[%s]" % (update.message.from_id.user_id, CID, update.message.message))

        if update.message.media is not None and (AUTHORIZED_USER and CID in user_ids):
            # When new media is sent to the chat, this function will be called
            is_video = telethon.utils.is_video(update.message.media)
            is_photo = TG_ALLOWED_PHOTO and (
                    telethon.utils.is_image(update.message.media) or telethon.utils.is_gif(update.message.media))
            is_torrent = is_file_torrent(update.message)
            if is_video is False and is_torrent is False and is_photo is False:
                return

            if is_subscription is True:
                message = await client.send_message(CID,
                                                    f'New file found on subscription chat {subscription.display_name},'
                                                    f' download file...')
            else:
                message = await update.reply('Download in queue...')

            if is_torrent:
                await queue.put([message, update.message, download_path_torrent, is_subscription, None])
            elif is_subscription is True:
                await queue.put(
                    [message, update.message, subscription.location, is_subscription, user_client.get_client()])
            else:
                current_messages.append((str(update.message.id) + ";" + str(message.id)))
                global current_timer
                if current_timer is not None:
                    current_timer.cancel()
                loop_ = asyncio.get_event_loop()
                current_timer = loop_.call_later(timeout, lambda: asyncio.ensure_future(answer_with_structure(message)))

        elif AUTHORIZED_USER and CID in user_ids:
            if is_subscription is False:
                await handle_regular_commands(update, CID, subs, auth_user_event_handler=user_event_handler)

        else:
            logger.info('UNAUTHORIZED USER: %s ', CID)
            if is_subscription is False:
                await update.reply('UNAUTHORIZED USER: %s \n add this ID to TG_AUTHORIZED_USER_ID' % CID)
            else:
                await client.send_message(CID, 'UNAUTHORIZED USER: %s \n add this ID to TG_AUTHORIZED_USER_ID' % CID)
    except Exception as e:
        if is_subscription is False:
            await update.reply('ERROR: ' + str(e))
        else:
            await tg_send_message('ERROR: ' + str(e))
        logger.info('EXCEPTION USER: %s ', str(e))


async def auth():
    for user_client in user_clients.values():
        u_client = user_client.get_client()
        await u_client.connect()
        authenticated = await u_client.is_user_authorized()
        user_client.set_authenticated(authenticated)
        if authenticated:
            u_client.add_event_handler(user_event_handler)
        elif user_client.get_user_id() in subs:
            await client.send_message(
                user_client.get_user_id(),
                f'⚠️ You have some subscriptions saved but you are not authenticated, please use /login command'
                f' to authenticate otherwise I will not be able to download new files from your subscriptions')


if __name__ == '__main__':
    tasks = []
    try:
        # Create concurrently tasks.
        loop = asyncio.get_event_loop()
        for i in range(number_of_parallel_downloads):
            task = loop.create_task(download_worker())
            tasks.append(task)

        # Start bot with token
        client.start(bot_token=str(bot_token))
        client.add_event_handler(handler)
        client.parse_mode = 'html'

        # Press Ctrl+C to stop
        loop.run_until_complete(client(functions.bots.SetBotCommandsRequest(
            scope=types.BotCommandScopeDefault(),
            lang_code='en',
            commands=[types.BotCommand(
                command='help',
                description='Get the list of available commands'
            ),
                types.BotCommand(
                    command='subscribe',
                    description='Listen for new messages in a channel or group'
                ),
                types.BotCommand(
                    command='version',
                    description='Get the version of the bot'
                ),
                types.BotCommand(
                    command='sendfiles',
                    description='Send files found in the /download/sendFiles folder'
                ),
                types.BotCommand(
                    command='id',
                    description='Get your Telegram ID'
                ),
                types.BotCommand(
                    command='newfolder',
                    description='Create a new folder'
                ),
                types.BotCommand(
                    command='login',
                    description='Authenticate your Telegram account in order to use the subscribe command'
                )]
        )))

        loop.run_until_complete(tg_send_message("Telethon Downloader Started: {}".format(VERSION)))
        splash()
        logger.info("%s" % VERSION)
        logger.info("********** START TELETHON DOWNLOADER **********")
        auth = loop.run_until_complete(auth())

        client.run_until_disconnected()
    finally:
        for task in tasks:
            task.cancel()
        # Stop Telethon
        client.disconnect()
        for u in user_clients.values():
            u.get_client().disconnect()
        logger.info("********** STOPPED **********")
