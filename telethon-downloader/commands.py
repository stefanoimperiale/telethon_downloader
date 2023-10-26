import asyncio
import os
import re

from telethon import Button
from telethon.tl.types import (KeyboardButtonRequestPeer, RequestPeerTypeBroadcast, RequestPeerTypeChat,
                               KeyboardButton, KeyboardButtonRow, ReplyKeyboardMarkup)

from clients import user_clients, client
from env import REQUEST_CHAT_ID, HELP, VERSION, TG_DL_TIMEOUT, TG_DOWNLOAD_PATH
from logger import logger
from utils import tg_send_file, execute_queries, contains_telegram_code


async def auth_user(user_id):
    await client.send_message(user_id, '👨‍💻 Click the button to require the authentication code', buttons=[
        Button.request_phone('📞 Set my phone number', resize=True, single_use=True, selective=True)])


async def handle_regular_commands(update, CID, subs, auth_user_event_handler):
    # -------------- CANCEL --------------
    if update.message.message == '❌ Cancel':
        await update.reply('Canceled', buttons=Button.clear())
    # -------------- HELP --------------
    elif update.message.message == '/help':
        await update.reply(HELP)
    # -------------- VERSION --------------
    elif update.message.message == '/version':
        await update.reply(VERSION)
    # -------------- ALIVE --------------
    elif update.message.message == '/alive':
        await update.reply('Keep-Alive')
    # -------------- ME --------------
    elif update.message.message == '/me' or update.message.message == '/id':
        await update.reply('id: {}'.format(CID))
        logger.info('me :[%s]' % CID)
    # -------------- SENDFILES --------------
    elif update.message.message == '/sendfiles':
        msg = await update.reply('Sending files...')
        # TODO Choose a folder to send
        base_path = os.path.join(TG_DOWNLOAD_PATH, 'sendFiles')
        sending = 0
        for root, subFolder, files in os.walk(base_path):
            subFolder.sort()
            files.sort()
            for item in files:
                if item.endswith('_process'):
                    # skip directories
                    continue
                sending += 1
                file_name_path = str(os.path.join(root, item))
                logger.info("SEND FILE :[%s]", file_name_path)
                await msg.edit('Sending {}...'.format(item))
                loop = asyncio.get_event_loop()
                task = loop.create_task(tg_send_file(CID, file_name_path, item))
                download_result = await asyncio.wait_for(task, timeout=TG_DL_TIMEOUT)
                if download_result:
                    logger.info("FILE SENT:[%s]", file_name_path)
                # shutil.move(file_name_path, file_name_path + "_process")
        await msg.edit('{} files submitted'.format(sending))
        logger.info("FILES SUBMITTED:[%s]", sending)

    # -------------- -------------- --------------
    # -------------- SUBSCRIPTIONS --------------
    # -------------- -------------- --------------
    else:
        u_client = user_clients[CID]
        if u_client and contains_telegram_code(
                update.message.message.replace(' ', '')) and u_client.get_phone() is not None:
            me = await u_client.get_client().sign_in(u_client.get_phone(),
                                                     code=update.message.message.replace(' ', '').replace('+', ''))
            u_client.set_authenticated(True)
            u_client.get_client().add_event_handler(auth_user_event_handler)
            return

        elif update.message.message == '/login':
            if u_client and u_client.is_authenticated() is True:
                await update.reply('⚠️ You are already authenticated')
                return
            else:
                await auth_user(CID)

        elif u_client is None or u_client.is_authenticated() is not True:
            await update.reply('⚠️ You are not authenticated. Please use /login command to authenticate')
            return

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
            await update.reply('Subscribe to automatically download on new messages', buttons=b)

        # -------------- REMOVE SUBSCRIPTIONS --------------
        elif update.message.message == '🗑 Remove subscription':
            if len(subs[CID]) == 0:
                await update.reply('⚠️ No subscriptions found')
            else:
                buttons = list(
                    map(lambda xy: [
                        Button.text(f'{xy.display_name} - {xy.chat_id}\n[{xy.location}]', resize=True,
                                    single_use=True)],
                        list(subs[CID].values())))
                await update.reply('👇 Select subscription to remove', buttons=[
                    [Button.text('❌ Cancel', resize=True, single_use=True)],
                    *buttons
                ])

        # -------------- LIST SUBSCRIPTIONS --------------
        elif update.message.message == '☰ List subscriptions':
            if len(subs[CID]) == 0:
                await update.reply('⚠️ No subscriptions found')
            else:
                subscriptions = '\n\n'.join(
                    [f'💬 <b>{v.display_name}</b>\n🗂️ <i>[{v.location}]</i>\n🆔 {v.chat_id}' for v in
                     list(subs[CID].values())])
                await update.reply('You are subscribed to the following channels/groups:\n\n'
                                   f'{subscriptions}')

        # -------------- SUBSCRIPTION DELETE --------------
        else:
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
                    await update.reply('✅ Subscription removed', buttons=Button.clear())
                else:
                    await update.reply('❌ Error removing subscription', buttons=Button.clear())
