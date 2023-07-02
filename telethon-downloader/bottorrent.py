#!/usr/bin/env python3

VERSION = "VERSION 3.1.11"
HELP = """
/help		: This Screen
/version	: Version  
/sendfiles	: send files found in the /download/sendFiles folder
/id			: YOUR ID TELEGRAM
"""
UPDATE = """
- DE HASTA 2000MB
- DESCARGA DE IMAGENES COMPRESS/UNCOMPRESS
- DESCARGA DE ARCHIVOS TORRENT EN CARPETA TG_DOWNLOAD_PATH_TORRENTS
- DESCARGA DE VIDEOS/LISTAS YOUTUBE.COM Y YOUTU.BE (SOLO ENVIANDO EL LINK DEL VIDEO/LISTA)
- UPLOAD FILES IN /download/sendFiles CON EL COMANDO /sendfiles
"""

import re
import shutil
import time
import asyncio
import zipfile
import sqlite3

# Imports Telethon
from telethon import TelegramClient, events, functions
from telethon.tl import types
from telethon.utils import get_extension, get_peer_id, resolve_id
from telethon.tl.custom import Button

from env import *
from logger import logger
from utils import getDownloadPath, getUsers, split_input, config_file, get_folders, send_folders_structure, \
    execute_queries
from youtube import youtube_download

session = SESSION

download_path = TG_DOWNLOAD_PATH
download_path_torrent = TG_DOWNLOAD_PATH_TORRENTS  # Directory where to save torrent file (if enabled). Connect with torrent client to start download.

AUTHORIZED_USER, usuarios = getUsers()
youtube_list = split_input(YOUTUBE_LINKS_SOPORTED)

queue = asyncio.Queue()
number_of_parallel_downloads = TG_MAX_PARALLEL
maximum_seconds_per_download = TG_DL_TIMEOUT

completed_path = PATH_COMPLETED

temp_completed_path = ''

db = sqlite3.connect("file::memory:?cache=shared")
db.execute(
    'CREATE TABLE locations(id INTEGER PRIMARY KEY,message_id varchar(50), location varchar(500) NOT NULL, display_location varchar(500))')


async def tg_send_message(msg):
    if AUTHORIZED_USER: await client.send_message(usuarios[0], msg)
    return True


async def tg_send_file(CID, file, name=''):
    async with client.action(CID, 'document') as action:
        await client.send_file(CID, file, caption=name, force_document=True, progress_callback=action.progress)


# Printing download progress
async def callback_progress(current, total, file_name, message, download_path_):
    value = (current / total) * 100
    format_float = "{:.2f}".format(value)
    int_value = int(float(format_float) // 1)
    try:
        if (int_value != 100) and (int_value % 20 == 0):
            await message.edit(f'Downloading {file_name} ... {format_float}% \ndownload in:\n{download_path_}')
    except Exception as e:
        logger.info('ERROR: %s' % e.__class__.__name__)
        logger.info('ERROR: %s' % str(e))


async def worker(name):
    while True:
        queue_item = await queue.get()
        update = queue_item[0]
        message = queue_item[1]
        final_folder = queue_item[2]

        real_id = get_peer_id(message.peer_id)
        CID, peer_type = resolve_id(real_id)
        # sender = await update.get_sender()
        # username = sender.username

        if AUTHORIZED_USER and CID not in usuarios:
            logger.info('USUARIO: %s NO AUTORIZADO', CID)
            continue
        ###
        file_name = 'FILENAME'
        if isinstance(message.media, types.MessageMediaPhoto):
            file_name = '{}{}'.format(message.media.photo.id, get_extension(message.media))
        elif any(x in message.message for x in youtube_list):
            try:
                url = message.message

                logger.info(f'INIT DOWNLOADING VIDEO YOUTUBE [{url}] ')
                loop = asyncio.get_event_loop()
                task = loop.create_task(youtube_download(url, update, final_folder))
                download_result = await asyncio.wait_for(task, timeout=YT_DL_TIMEOUT)
                logger.info(f'FINIT DOWNLOADING VIDEO YOUTUBE [{url}] [{download_result}] ')
                queue.task_done()
                continue
            except Exception as e:
                logger.info('ERROR: %s DOWNLOADING YT: %s' % (e.__class__.__name__, str(e)))
                await update.edit('Error!')
                message = await message.edit('ERROR: %s DOWNLOADING YT: %s' % (e.__class__.__name__, str(e)))
                queue.task_done()
                continue
        else:
            attributes = message.media.document.attributes
            for attr in attributes:
                if isinstance(attr, types.DocumentAttributeFilename):
                    file_name = attr.file_name
                elif message.message:
                    file_name = re.sub(r'[^A-Za-z0-9 -!\[\]\(\)]+', ' ', message.message)
                else:
                    file_name = time.strftime('%Y%m%d %H%M%S', time.localtime())
                    file_name = '{}{}'.format(message.media.document.id, get_extension(message.media))
        # _download_path, _complete_path = getDownloadPath(file_name, CID)
        file_path = os.path.join(final_folder, file_name)

        logger.info(f"getDownloadPath FILE [{file_name}] to [{file_path}]")
        await update.edit(f'Downloading {file_name} \ndownload in:\n{file_path}')
        # time.sleep(1)
        logger.info('Downloading... ')
        mensaje = 'STARTING DOWNLOADING %s [%s] BY [%s]' % (
            time.strftime('%d/%m/%Y %H:%M:%S', time.localtime()), file_path, CID)
        logger.info(mensaje)
        try:
            loop = asyncio.get_event_loop()
            if TG_PROGRESS_DOWNLOAD == True or TG_PROGRESS_DOWNLOAD == 'True':
                task = loop.create_task(client.download_media(message, file_path,
                                                              progress_callback=lambda x,y:callback_progress(x, y,
                                                                                                      file_name,
                                                                                                      update,
                                                                                                      file_path)))
            else:
                task = loop.create_task(client.download_media(message, file_path))
            download_result = await asyncio.wait_for(task, timeout=maximum_seconds_per_download)
            end_time = time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())
            end_time_short = time.strftime('%H:%M', time.localtime())
            final_path = os.path.split(download_result)[1]
            if TG_UNZIP_TORRENTS:
                if zipfile.is_zipfile(final_path):
                    with zipfile.ZipFile(final_path, 'r') as zipObj:
                        for fileName in zipObj.namelist():
                            if fileName.endswith('.torrent'):
                                zipObj.extract(fileName, download_path_torrent)
                                logger.info("UNZIP TORRENTS [%s] to [%s]" % (fileName, download_path_torrent))

            ######
            mensaje = 'DOWNLOAD FINISHED %s [%s] => [%s]' % (end_time, file_name, final_path)
            logger.info(mensaje)
            await update.edit('Downloading finished:\n%s \nIN: %s\nat %s' % (file_name, final_path, end_time_short))
        except asyncio.TimeoutError:
            logger.info('[%s] Time exceeded %s' % (file_name, time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())))
            await update.edit('Error!')
            message = await update.reply('ERROR: Time exceeded downloading this file')
        except Exception as e:
            logger.critical(e)
            logger.info('[EXCEPCION]: %s' % (str(e)))
            logger.info('[%s] Excepcion %s' % (file_name, time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())))
            await update.edit('Error!')
            await message.reply('ERROR: %s downloading : %s' % (e.__class__.__name__, str(e)))

        # Unidad de trabajo terminada.
        queue.task_done()


client = TelegramClient(session, api_id, api_hash, proxy=None, request_retries=10, flood_sleep_threshold=120)


@client.on(events.CallbackQuery)
async def callback(event):
    # chat = await event.get_chat()
    logger.info(event)
    message_id = event.data.decode('utf-8')
    if message_id == 'CANCEL':
        execute_queries(db, [(f'DELETE FROM locations', ())])
        return await event.edit('Canceled')
    elif message_id.startswith('STOP,'):
        message_id = message_id.split(',')[1]
        media_id, final_path = \
        execute_queries(db, [(f'SELECT message_id, location FROM locations WHERE id=?', (message_id,)),
                             (f'DELETE FROM locations', ())])[0][0]
        result = await client(functions.messages.GetMessagesRequest(id=[int(media_id)]))
        message = result.messages[0]
        await queue.put([event, message, final_path])
    elif message_id.startswith('NEW,'):
        message_id = message_id.split(',')[1]
        await event.edit('Insert new folder name',
                         buttons=[[Button.inline('Back ', f'{message_id}'), Button.inline('❌ Cancel', data='CANCEL')]])
    else:
        media_id, base_path = \
        execute_queries(db, [(f'SELECT message_id, location FROM locations WHERE id=?', (message_id,)),
                             (f'DELETE FROM locations', ())])[0][0]
        await send_folders_structure(event, media_id, db, base_path)


@events.register(events.NewMessage)
async def handler(update):
    try:
        real_id = get_peer_id(update.message.peer_id)
        CID, peer_type = resolve_id(real_id)
        is_torrent= False

        if update.message.from_id is not None:
            logger.info(
                "USER ON GROUP => U:[%s]G:[%s]M:[%s]" % (update.message.from_id.user_id, CID, update.message.message))

        if update.message.media is not None and (AUTHORIZED_USER and CID in usuarios):
            # When new media is sent to the chat, this function will be called
            file_name = 'NONAME'

            if isinstance(update.message.media, types.MessageMediaPhoto):
                file_name = '{}{}'.format(update.message.media.photo.id, get_extension(update.message.media))
                logger.info("MessageMediaPhoto  [%s]" % file_name)
            elif any(x in update.message.message for x in youtube_list):
                file_name = 'YOUTUBE VIDEO'
            else:
                if update.message.media.document.mime_type == 'application/x-bittorrent':
                    is_torrent = True
                attributes = update.message.media.document.attributes
                for attr in attributes:
                    if isinstance(attr, types.DocumentAttributeFilename):
                        file_name = attr.file_name
                    elif update.message.message:
                        file_name = re.sub(r'[^A-Za-z0-9 -!\[\]\(\)]+', ' ', update.message.message)

            messageLog = 'DOWNLOAD IN QUEUE [%s] [%s]' % (
                time.strftime('%d/%m/%Y %H:%M:%S', time.localtime()), file_name)
            logger.info(messageLog)
            message = await update.reply('Download in queue...')
            if is_torrent:
                await queue.put([message, update.message, download_path_torrent])
            else:
                await send_folders_structure(message, update.message.id, db)
        elif AUTHORIZED_USER and CID in usuarios:
            if update.message.message == '/help':
                await update.reply(HELP)
            elif update.message.message == '/version':
                await update.reply(VERSION)
            elif update.message.message == '/alive':
                await update.reply('Keep-Alive')
            elif update.message.message == '/me' or update.message.message == '/id':
                await update.reply('id: {}'.format(CID))
                logger.info('me :[%s]' % CID)
            elif update.message.message == '/sendfiles':
                msg = await update.reply('Sending files...')
                # TODO Choose a folder to send
                basepath = os.path.join(download_path, 'sendFiles')
                sending = 0
                for root, subFolder, files in os.walk(basepath):
                    subFolder.sort()
                    files.sort()
                    for item in files:
                        if item.endswith('_process'):
                            # skip directories
                            continue
                        sending += 1
                        fileNamePath = str(os.path.join(root, item))
                        logger.info("SEND FILE :[%s]", fileNamePath)
                        await msg.edit('Sending {}...'.format(item))
                        loop = asyncio.get_event_loop()
                        task = loop.create_task(tg_send_file(CID, fileNamePath, item))
                        download_result = await asyncio.wait_for(task, timeout=maximum_seconds_per_download)
                        if download_result:
                            logger.info("FILE SENT:[%s]", fileNamePath)
                        # shutil.move(fileNamePath, fileNamePath + "_process")
                await msg.edit('{} files submitted'.format(sending))
                logger.info("FILES SUBMITTED:[%s]", sending)
            else:
                # Check if reply of new directory command
                async for message in client.iter_messages(CID, limit=1):
                    print(message.id, message.text)

        else:
            logger.info('UNAUTHORIZED USER: %s ', CID)
            await update.reply('UNAUTHORIZED USER: %s \n add this ID to TG_AUTHORIZED_USER_ID' % CID)
    except Exception as e:
        await update.reply('ERROR: ' + str(e))
        logger.info('EXCEPTION USER: %s ', str(e))


if __name__ == '__main__':
    tasks = []
    try:
        # Create concurrently tasks.
        loop = asyncio.get_event_loop()
        for i in range(number_of_parallel_downloads):
            task = loop.create_task(worker('worker-{%i}' % i))
            tasks.append(task)

        # Start bot with token
        client.start(bot_token=str(bot_token))
        client.add_event_handler(handler)

        # Press Ctrl+C to stop
        loop.run_until_complete(tg_send_message("Telethon Downloader Started: {}".format(VERSION)))
        logger.info("%s" % VERSION)
        config_file()
        logger.info("********** START TELETHON DOWNLOADER **********")

        client.run_until_disconnected()
    finally:
        for task in tasks:
            task.cancel()
        # Stop Telethon
        client.disconnect()
        logger.info("********** STOPPED **********")
