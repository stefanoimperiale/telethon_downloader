import asyncio
import os
import re
import time
import zipfile

from telethon.tl.custom import Message
from telethon.tl.types import DocumentAttributeFilename, MessageMediaPhoto
from telethon.utils import get_peer_id, resolve_id, get_extension

from clients import client, queue
from env import TG_DL_TIMEOUT, TG_PROGRESS_DOWNLOAD, TG_UNZIP_TORRENTS, YOUTUBE_LINKS_SOPORTED
from logger import logger
from model.timer import Timer
from utils import split_input, progress_bar, tg_reply_message
from youtube import download_youtube_video

youtube_list = split_input(YOUTUBE_LINKS_SOPORTED)


def get_file_name(message: Message) -> str:
    file_name = time.strftime('%Y%m%d %H%M%S', time.localtime())
    if isinstance(message.media, MessageMediaPhoto):
        file_name = '{}{}'.format(message.media.photo.id, get_extension(message.media))
    else:
        attributes = message.media.document.attributes
        for attr in attributes:
            if isinstance(attr, DocumentAttributeFilename):
                file_name = attr.file_name
            elif message.message:
                file_name = re.sub(r'[^A-Za-z0-9 -!\[\]()]+', ' ', message.message)
            else:
                file_name = '{}{}'.format(message.media.document.id, get_extension(message.media))
    return file_name


# Printing download progress
async def callback_progress(current: int, total: int, message, download_path: str, start: float, timer: Timer):
    speed = "%.2f Mbps" % (current // (time.perf_counter() -
                                       start) / 100000)
    progress = progress_bar(current, total, suffix=speed)
    try:
        if timer.can_send() or current == total:
            await client.edit_message(message,
                                      f'⬇️ Downloading in: <i>"{download_path}"</i>'
                                      f'\n\n{progress}')
    except Exception as e:
        logger.info('ERROR: %s' % e.__class__.__name__)
        logger.info('ERROR: %s' % str(e))


async def download_worker():
    while True:
        queue_item = await queue.get()
        update = queue_item[0]
        message = queue_item[1]
        final_folder = queue_item[2]
        is_subscription = queue_item[3]
        user_client = queue_item[4]
        timer = Timer()
        loop = asyncio.get_event_loop()

        real_id = get_peer_id(message.peer_id)
        CID, peer_type = resolve_id(real_id)

        ###
        if any(x in message.message for x in youtube_list):
            await download_youtube_video(update, message, final_folder, loop)
            queue.task_done()
            continue
        file_name = get_file_name(message)
        file_path = os.path.join(final_folder, file_name)

        logger.info(f"getDownloadPath FILE [{file_name}] to [{file_path}]")

        await client.edit_message(update, f'Downloading in:\n<i>"{file_path}"</i>')
        await asyncio.sleep(1)

        logger.info('Downloading... ')
        logger.info('STARTING DOWNLOADING %s [%s] BY [%s]' % (
            time.strftime('%d/%m/%Y %H:%M:%S', time.localtime()), file_path, CID))

        try:
            loop = asyncio.get_event_loop()
            download_client = user_client if is_subscription else client
            if TG_PROGRESS_DOWNLOAD is True or TG_PROGRESS_DOWNLOAD == 'True':
                start = time.perf_counter()
                task = loop.create_task(download_client.download_media(message, file_path,
                                                                       progress_callback=lambda x, y: callback_progress(
                                                                           x, y,
                                                                           update,
                                                                           file_path,
                                                                           start,
                                                                           timer)))
            else:
                task = loop.create_task(download_client.download_media(message, file_path))

            await asyncio.wait_for(task, timeout=TG_DL_TIMEOUT)
            end_time = time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())
            end_time_short = time.strftime('%H:%M', time.localtime())
            # final_path = os.path.split(download_result)[1]

            if TG_UNZIP_TORRENTS and zipfile.is_zipfile(file_path):
                with zipfile.ZipFile(file_path, 'r') as zipObj:
                    for fileName in zipObj.namelist():
                        if fileName.endswith('.torrent'):
                            zipObj.extract(fileName, file_path)
                            logger.info("UNZIP TORRENTS [%s] to [%s]" % (fileName, file_path))

            ######
            logger.info('DOWNLOAD FINISHED %s [%s] => [%s]' % (end_time, file_name, file_path))
            await asyncio.sleep(1)
            await client.edit_message(update, '👍 Downloading finished:\n%s \nIN: %s\nat %s' % (
                file_name, file_path, end_time_short))

        except asyncio.TimeoutError:
            logger.info('[%s] Time exceeded %s' % (file_name, time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())))
            await tg_reply_message(CID, update, 'ERROR: Time exceeded downloading this file')
        except Exception as e:
            logger.critical(e)
            logger.info('[EXCEPTION]: %s' % (str(e)))
            logger.info('[%s] Exception %s' % (file_name, time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())))
            await tg_reply_message(CID, update, 'ERROR: %s downloading : %s' % (e.__class__.__name__, str(e)))

        # Queue task done
        queue.task_done()
