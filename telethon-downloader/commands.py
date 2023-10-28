import asyncio
import os
import re

from telethon import Button, functions
from telethon.tl.types import (KeyboardButtonRequestPeer, RequestPeerTypeBroadcast, RequestPeerTypeChat,
                               KeyboardButton, KeyboardButtonRow, ReplyKeyboardMarkup, InputMessageID)

from clients import user_clients, client, queue
from env import REQUEST_CHAT_ID, HELP, VERSION, PATH_COMPLETED
from logger import logger
from model.subscription import Subscription
from utils import execute_queries, contains_telegram_code, send_folders_structure, replace_right, tg_send_message, \
    tg_reply_message, get_last_client_message, insert_last_message


async def auth_user(user_id):
    await tg_send_message(user_id, '👨‍💻 Click the button to require the authentication code', buttons=[
        Button.request_phone('📞 Set my phone number', resize=True, single_use=True, selective=True)],
                          operation='login')


def required_auth(message, last_message):
    return (message.message == '/subscribe'
            or message.message == '🗑 Remove subscription'
            or message.message == '☰ List subscriptions'
            or last_message is not None and last_message.operation == 'remove-subscription'
            )


async def put_in_queue(final_path: str, messages_id: str):
    message_id, event_id = messages_id.split(';')
    result = await client(
        functions.messages.GetMessagesRequest(id=[InputMessageID(int(message_id)), InputMessageID(int(event_id))]))
    message = result.messages[0]
    event = result.messages[1]
    await queue.put([event, message, final_path, False, None])


async def handle_folder_choose_operation(message_id, user_id, event, subs):
    message_id = message_id.split(',')[1]
    media_id, final_path, messages, operation = \
        execute_queries([(f'SELECT message_id, location, messages_ids, operation '
                          f'FROM locations '
                          f'WHERE id=? and user_id=?',
                          (message_id, user_id))])[0][0]
    if operation != 'send' and operation != 'new-folder':
        execute_queries([(f'DELETE FROM locations where user_id=? and message_id=?', (user_id, media_id))])
    if operation == 'download':
        producers = list(map(lambda x: asyncio.create_task(put_in_queue(final_path, x)), messages.split(',')))
        await asyncio.gather(*producers)
    elif operation == 'subscription':
        title = replace_right(messages, f',{media_id}', '', 1)
        chat_id = media_id
        saved = execute_queries([(
            'INSERT INTO subscriptions(user_id, chat_id, location, display_name) VALUES (?, ?, ?, ?)',
            (user_id, chat_id, final_path, title))])[0]
        if saved is not False:
            subs[int(user_id)][int(chat_id)] = Subscription(int(user_id), int(chat_id), final_path, title)
            await event.edit('🎉 Subscription created, I will download new files from this chat'
                             f' when a new media is sent inside <i>"{final_path}"</pre>')
        else:
            await event.edit('❗ Error saving chat id, try again')
    elif operation == 'send':
        files = next(os.walk(final_path), (None, None, []))[2]
        if (len(files)) == 0:
            await event.edit('❌ No files found in the folder',
                             buttons=[[Button.inline('⬅️ Back', data=f'BACKIN,{message_id}'),
                                       Button.inline('❌ Cancel', data=f'CANCEL,{message_id}')]])
        else:
            files.sort(key=str.casefold)
            await event.edit('Choose file or folder to download', buttons=[
                [Button.inline('⬅️ Back', data=f'BACKIN,{message_id}'),
                 Button.inline('❌ Cancel', data=f'CANCEL,{message_id}')],
                [Button.inline(f'🗂️ All files in the folder', data=f'FOLD,{message_id}')],
                *list(map(lambda x: [Button.inline(f'📄 {x[1]}', f'FILE,{message_id},{x[0]}')], enumerate(files))),
            ])
    elif operation == 'new-folder':
        insert_last_message(user_id, event, 'new-folder',
                            (final_path, 'finish' if operation == 'new-folder' else 'back'))
        await event.edit('Insert new folder name',
                         buttons=[[Button.inline('⬅️ Back', data=f'BACK,{message_id}'),
                                   Button.inline('❌ Cancel', data=f'CANCEL,{message_id}')]])


async def handle_regular_commands(update, CID, subs, auth_user_event_handler, callback_handler):
    # -------------- CANCEL --------------
    if update.message.message == '❌ Cancel':
        await tg_reply_message(CID, update, 'Canceled', buttons=Button.clear())
    # -------------- HELP --------------
    elif update.message.message == '/help':
        await tg_reply_message(CID, update, HELP)
    # -------------- VERSION --------------
    elif update.message.message == '/version':
        await tg_reply_message(CID, update, VERSION)
    # -------------- ALIVE --------------
    elif update.message.message == '/alive':
        await tg_reply_message(CID, update, 'Keep-Alive')
    # -------------- ME --------------
    elif update.message.message == '/me' or update.message.message == '/id':
        await tg_reply_message(CID, update, 'id: {}'.format(CID))
        logger.info('me :[%s]' % CID)
    # -------------- SENDFILES --------------
    elif update.message.message == '/download':
        message = await tg_send_message(CID, '📂 Choose file or folder to download')
        await send_folders_structure(message, CID, [f'{message.id}'], operation='send',
                                     custom_message='📂 Choose file or folder to download')
    elif update.message.message == '/newfolder':
        message = await tg_send_message(CID, '📂 Choose where to create the new folder', operation='new-folder',
                                        arg=(PATH_COMPLETED, 'finish'))
        await send_folders_structure(message, CID, [f'{message.id}'], operation='new-folder',
                                     custom_message='📂 Choose where to create the new folder')

    else:
        last_message = get_last_client_message(CID)
        u_client = user_clients[CID]

        # -------------- AUTHENTICATION CODE --------------
        if (last_message and last_message.operation == 'login'
                and u_client
                and contains_telegram_code(update.message.message.replace(' ', ''))
                and u_client.get_phone() is not None):
            await u_client.get_client().sign_in(u_client.get_phone(),
                                                code=update.message.message.replace(' ', '').replace('+', ''))
            u_client.set_authenticated(True)
            u_client.get_client().add_event_handler(auth_user_event_handler)
            await tg_send_message(CID, '✅ You are authenticated')

        # -------------- LOGIN --------------
        elif update.message.message == '/login':
            if u_client and u_client.is_authenticated() is True:
                await tg_reply_message(CID, update, '⚠️ You are already authenticated')
                return
            else:
                await auth_user(CID)

        # -------------- NEW FOLDER --------------
        elif last_message is not None and last_message.operation == 'new-folder':
            try:
                os.makedirs(os.path.join(last_message.arg[0], update.message.message), exist_ok=True)
                await last_message.message.edit('✅ Folder created')
                await update.delete()
                await asyncio.sleep(1)
                if last_message.arg[1] == 'back':
                    data = last_message.message.data.decode('utf-8').split(',')
                    await callback_handler(last_message.message, f'BACKIN,{data[1]}')
            except Exception as e:
                logger.error(e)
                await last_message.message.edit('❌ Error creating folder, try again')

        # -------------- AUTH COMMANDS --------------
        elif required_auth(update.message, last_message):
            if u_client is None or u_client.is_authenticated() is not True:
                await tg_reply_message(CID, update,
                                       '⚠️ You are not authenticated. Please use /login command to authenticate')

            # -------------- -------------- --------------
            # -------------- SUBSCRIPTIONS --------------
            # -------------- -------------- --------------
            elif update.message.message == '/subscribe':
                channels_k = KeyboardButtonRequestPeer('📣 Subscribe to Channel', REQUEST_CHAT_ID,
                                                       RequestPeerTypeBroadcast())
                groups_k = KeyboardButtonRequestPeer('👯‍♂️ Subscribe to Group', REQUEST_CHAT_ID + 1,
                                                     RequestPeerTypeChat())
                list_s = KeyboardButton('☰ List subscriptions')
                remove_s = KeyboardButton('🗑 Remove subscription')
                b = ReplyKeyboardMarkup(
                    [KeyboardButtonRow([channels_k, groups_k]), KeyboardButtonRow([list_s, remove_s])],
                    resize=True, single_use=True)
                await tg_reply_message(CID, update, 'Subscribe to automatically download on new messages', buttons=b)

            # -------------- REMOVE SUBSCRIPTIONS --------------
            elif update.message.message == '🗑 Remove subscription':
                if len(subs[CID]) == 0:
                    await tg_reply_message(CID, update, '⚠️ No subscriptions found')
                else:
                    buttons = list(
                        map(lambda xy: [
                            Button.text(f'{xy.display_name} - {xy.chat_id}\n[{xy.location}]', resize=True,
                                        single_use=True)],
                            list(subs[CID].values())))
                    await tg_reply_message(CID, update, '👇 Select subscription to remove', buttons=[
                        [Button.text('❌ Cancel', resize=True, single_use=True)],
                        *buttons
                    ], operation='remove-subscription')

            # -------------- LIST SUBSCRIPTIONS --------------
            elif update.message.message == '☰ List subscriptions':
                if len(subs[CID]) == 0:
                    await tg_reply_message(CID, update, '⚠️ No subscriptions found')
                else:
                    subscriptions = '\n\n'.join(
                        [f'💬 <b>{v.display_name}</b>\n🗂️ <i>[{v.location}]</i>\n🆔 {v.chat_id}' for v in
                         list(subs[CID].values())])
                    await tg_reply_message(CID, update, 'You are subscribed to the following channels/groups:\n\n'
                                                        f'{subscriptions}')

            # -------------- SUBSCRIPTION DELETE --------------
            elif last_message is not None and last_message.operation == 'remove-subscription':
                pattern = r'-\s(\d+)'
                text = update.message.message
                last_match = None
                number = None
                for match in re.finditer(pattern, text):
                    last_match = match

                if last_match:
                    number = last_match.group(1)
                    print(number)

                if number is not None and CID in subs and int(number) in subs[CID]:
                    delete = execute_queries([('DELETE FROM subscriptions WHERE user_id =? AND chat_id=?',
                                               (CID, int(number)))])[0]
                    if delete is not False:
                        subs[CID].pop(int(number))
                        await tg_reply_message(CID, update, '✅ Subscription removed', buttons=Button.clear())
                    else:
                        await tg_reply_message(CID, update, '❌ Error removing subscription', buttons=Button.clear())
        else:
            await tg_reply_message(CID, update, '⚠️ Command not found, use /help to see the available commands')
