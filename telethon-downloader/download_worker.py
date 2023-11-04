import asyncio
import os
import re
import time
import uuid
import zipfile
from collections import defaultdict

import telethon.utils
from telethon import types, Button
from telethon.tl.custom import Message
from telethon.tl.types import DocumentAttributeFilename, MessageMediaPhoto
from telethon.utils import get_peer_id, resolve_id, get_extension

from clients import client, queue, current_tasks
from env import TG_DL_TIMEOUT, TG_PROGRESS_DOWNLOAD, TG_UNZIP_TORRENTS, YOUTUBE_LINKS_SOPORTED
from logger import logger
from model.timer import Timer
from utils import split_input, progress_bar, tg_reply_message, sizeof_fmt
from youtube import download_youtube_video
from model.current_task import CurrentTask

youtube_list = split_input(YOUTUBE_LINKS_SOPORTED)

# dictionary of locks
locks = defaultdict(asyncio.Lock)


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
async def callback_progress(current: int, total: int, task_id, message, download_path: str, start: float, timer: Timer):
    speed = "%.2f Mbps" % (current // (time.perf_counter() -
                                       start) / 100000)
    progress = progress_bar(current, total, suffix=speed)
    try:
        if timer.can_send() or current == total:
            await client.edit_message(message,
                                      f'⬇️ Downloading in: <i>"{download_path}"</i>'
                                      f'\n\n{progress}', buttons=[Button.inline('⏸️ Pause', data=f'PAUSE,{task_id}'),
                                                                  Button.inline('✖️ Cancel',
                                                                                data=f'D_CANCEL,{task_id}')])
    except Exception as e:
        logger.info('ERROR: %s' % e.__class__.__name__)
        logger.info('ERROR: %s' % str(e))


async def download_with_pause(download_client, message, file_path, offset, task_id, update, callback=None):
    if isinstance(message, types.Message):
        message = message.media
    if isinstance(message, types.MessageMediaDocument):
        doc = message.document
    elif isinstance(message, types.MessageMediaPhoto):
        doc = message.photo
    else:
        logger.info('Unsupported message type')
        return

    if isinstance(doc, types.Document):
        total = doc.size
    elif isinstance(doc, types.Photo):
        total = telethon.utils._photo_size_byte_count(doc)
    else:
        logger.info('Unsupported message type')
        return

    lock_name = file_path + '.lock'
    try:
        lock = locks[lock_name]
        async with lock:
            with open(file_path, 'ab') as fd:
                # ^ append
                async for chunk in download_client.iter_download(doc, offset=offset):
                    #                                                 ^~~~~~~~~~~~~ resume from offset
                    offset += len(chunk)
                    if callback:
                        await callback(offset, total)
                    fd.write(chunk)

    except asyncio.CancelledError as e:
        if str(e) != 'PAUSE':
            if os.path.exists(file_path):
                os.unlink(file_path)
            await client.edit_message(update, '❌ Download cancelled')
        else:
            await client.edit_message(update, '⏸️ Download paused\n %s/%s' % (sizeof_fmt(offset), sizeof_fmt(total)),
                                      buttons=[Button.inline('▶️ Resume', data=f'RESUME,{task_id}'),
                                               Button.inline('✖️ Cancel', data=f'D_CANCEL,{task_id}')])
        return True
    except Exception as e:
        logger.info('ERROR: %s' % e.__class__.__name__)
        logger.info('ERROR: %s' % str(e))
        await client.edit_message(update, 'ERROR: %s downloading : %s' % (e.__class__.__name__, str(e)))
        return True
    finally:
        locks.pop(lock_name, None)


async def download_worker():
    while True:
        queue_item = await queue.get()
        update = queue_item[0]
        message = queue_item[1]
        final_folder = queue_item[2]
        is_subscription = queue_item[3]
        user_client = queue_item[4]
        task_id_old = queue_item[5] if len(queue_item) > 5 else None
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
        task_id = task_id_old if task_id_old else uuid.uuid4().hex

        try:
            await client.edit_message(update, f'Downloading in:\n<i>"{file_path}"</i>',
                                      buttons=[Button.inline('⏸️ Pause', data=f'PAUSE,{task_id}'),
                                               Button.inline('✖️ Cancel', data=f'D_CANCEL,{task_id}')])
            await asyncio.sleep(1)

            logger.info('Downloading... ')
            logger.info('STARTING DOWNLOADING %s [%s] BY [%s]' % (
                time.strftime('%d/%m/%Y %H:%M:%S', time.localtime()), file_path, CID))
            loop = asyncio.get_event_loop()
            download_client = user_client if is_subscription else client

            try:
                offset = os.path.getsize(file_path)
            except OSError:
                offset = 0
            if TG_PROGRESS_DOWNLOAD is True or TG_PROGRESS_DOWNLOAD == 'True':
                start = time.perf_counter()
                callback = (lambda x, y: callback_progress(
                    x, y,
                    task_id,
                    update,
                    file_path,
                    start,
                    timer))
                # if offset > 0:
                task = loop.create_task(
                    download_with_pause(download_client, message, file_path, offset, task_id, update, callback))
                # else:
                #     task = loop.create_task(download_client.download_media(message, file_path,
                #                                                            progress_callback=callback))

            # elif offset > 0:
            #     task = loop.create_task(download_client.download_media(message, file_path))
            else:
                task = loop.create_task(
                    download_with_pause(download_client, message, file_path, offset, task_id, update))
            # await asyncio.sleep(5)
            # task.cancel()
            current_tasks[CID][task_id] = CurrentTask(task,
                                                      [update, message, final_folder, is_subscription, user_client],
                                                      file_path, 'DOWNLOAD')
            err = await asyncio.wait_for(task, timeout=TG_DL_TIMEOUT)
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
            if err is None:
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
        finally:
            current_tasks.pop(task_id, None)

        # Queue task done
        queue.task_done()
