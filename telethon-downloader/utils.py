import asyncio
import os
import re
import time
from typing import List, Tuple, Any, Union, Literal

from telethon.tl.custom import Button

from clients import client
from database import db
from env import PATH_COMPLETED, TG_AUTHORIZED_USER_ID, AUTHORIZED_USER, user_ids, TG_DL_TIMEOUT
from logger import logger
from model.timer import Timer


def splash() -> None:
    """ Displays splash screen """
    logger.info('''    
----------------------------------------------
 _       _      _   _
| |_ ___| | ___| |_| |__   ___  _ __
| __/ _ \\ |/ _ \\ __| '_ \\ / _ \\| '_ \\
| ||  __/ |  __/ |_| | | | (_) | | | |
 \\__\\___|_|\\___|\\__|_| |_|\\___/|_| |_|

     _                     _                 _
  __| | _____      ___ __ | | ___   __ _  __| | ___ _ __
 / _` |/ _ \\ \\ /\\ / / '_ \\| |/ _ \\ / _` |/ _` |/ _ \\ '__|
| (_| | (_) \\ V  V /| | | | | (_) | (_| | (_| |  __/ |
 \\__,_|\\___/ \\_/\\_/ |_| |_|_|\\___/ \\__,_|\\__,_|\\___|_|


----------------------------------------------
    ''')


def split_input(input_) -> List[str]:
    """ Returns a list of inputted strings """
    inputs = []
    if TG_AUTHORIZED_USER_ID.strip() == '':
        return inputs
    else:
        inputs = list(map(str, input_.replace(" ", "").split(',')))
        return inputs


def create_directory(download_path: str) -> None:
    try:
        os.makedirs(download_path, exist_ok=True)
    except Exception as e:
        logger.info(f'create_directory Exception : {download_path} [{e}]')


def sizeof_fmt(num, suffix="b"):
    for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def progress_bar(count_value, total, suffix=''):
    bar_length = 20
    filled_up_length = int(round(bar_length * count_value / float(total)))
    percentage = round(100.0 * count_value / float(total), 1)
    bar = '=' * filled_up_length + '-' * (bar_length - filled_up_length)
    return '\r%s%s [%s] %s\r\n\r%s/%s' % (percentage, '%', bar, suffix, sizeof_fmt(count_value), sizeof_fmt(total))


async def upload_progress(action, current, total, event, start, timer, total_size, len_files):
    try:
        if total_size is not None:
            total = len_files
            current = (current / float(total)) * total_size
            total = total_size
        action.progress(current, total)
        speed = "%.2f Mbps" % (current // (time.perf_counter() -
                                           start) / 100000)
        progress = progress_bar(current, total, suffix=speed)
        if timer.can_send() or current == total:
            await event.edit(f'⬆️ Uploading files...\n\n{progress}')
    except Exception as e:
        logger.info('ERROR: %s' % e.__class__.__name__)
        logger.info('ERROR: %s' % str(e))


async def send_file(CID, file, start, timer, action, total_size=None, len_files=1, name=''):
    event = await client.send_message(CID, 'Starting upload...')
    await client.send_file(CID, file, caption=name, force_document=True,
                           progress_callback=lambda curr, tot: upload_progress(action, curr, tot,
                                                                               event, start,
                                                                               timer,
                                                                               total_size, len_files))


async def tg_send_file(CID, file, total_size, name=''):
    async with client.action(CID, 'document') as action:
        loop = asyncio.get_event_loop()
        start = time.perf_counter()
        timer = Timer()
        task = loop.create_task(send_file(CID, file, start, timer, action, total_size, len(file), name))
        await asyncio.wait_for(task, timeout=TG_DL_TIMEOUT)
        await asyncio.sleep(1)


def get_folders(message_id, user_id, message_media_ids, path, operation):
    """ Returns a list of folders in the path """
    folders = []
    for f in os.listdir(path):
        if os.path.isdir(os.path.join(path, f)):
            folders.append((message_id, user_id, os.path.join(path, f), f, message_media_ids, operation))
    return folders


def execute_queries(queries: List[Tuple[str, Tuple[Any, ...]]]):
    res = []
    try:
        with db:
            cur = db.cursor()
            for (query, args) in queries:
                res.append(list(cur.execute(query, args)))
            return res
    except Exception as why:
        logger.error(why)
        return False


async def send_folders_structure(message_to_edit, user_id, message_media_ids, base_path=PATH_COMPLETED,
                                 operation: Union[
                                     Literal['download'], Literal['subscription'], Literal['send']] = 'download'):
    message_media_id = message_media_ids[-1]
    messages_join = ','.join(message_media_ids)
    dirs = get_folders(message_media_id, user_id, messages_join, base_path, operation)
    try:
        with db:
            cur = db.cursor()
            # Insert sub folders
            cur.executemany(
                'INSERT INTO locations(message_id, user_id, location,display_location, messages_ids, operation) '
                'VALUES (?, ?, ?, ?, ?, ?)', dirs)
            dirs = cur.execute('SELECT id, display_location FROM locations where message_id=? and user_id=?',
                               (f'{message_media_id}', f'{user_id}'))
            dirs = sorted(dirs, key=lambda x: x[1])
            buttons = list(
                map(lambda xy: Button.inline(f'{xy[1]}', data=f'{xy[0]}'), dirs))
            buttons = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]  # Max 3 buttons per row

            # Insert current dir
            cur.execute('INSERT INTO locations'
                        '(message_id, user_id, location, display_location, messages_ids, operation) '
                        'VALUES (?, ?, ?, ?, ?, ?)',
                        (message_media_id, user_id, base_path, base_path, messages_join, operation))
            current_id = cur.lastrowid
            is_root = False
            if base_path == PATH_COMPLETED:
                is_root = True

            operation_buttons = [Button.inline('➡️ This dir',
                                               data=f'STOP,{current_id}'),
                                 Button.inline('❌ Cancel', data=f'CANCEL,{current_id}')]
            if not is_root:
                operation_buttons.insert(1, Button.inline('⬅️ Back', data=f'BACK,{current_id}'))
            await message_to_edit.edit(f'📂 Choose download folder \n (current dir: {base_path})',
                                       buttons=buttons + [operation_buttons])
    except Exception as why:
        logger.error(why)
        return False


def is_file_torrent(message):
    return message.media.document.mime_type == 'application/x-bittorrent' or (
            message.file.name is not None and message.file.name.lower().strip().endswith('.torrent'))


def replace_right(source, target, replacement, replacements=None):
    return replacement.join(source.rsplit(target, replacements))


async def tg_send_message(msg):
    if AUTHORIZED_USER:
        return await client.send_message(user_ids[0], msg)
    else:
        await client.send_message(user_ids[0], 'ERROR: NO AUTHORIZED USER')
        raise Exception('ERROR: NO AUTHORIZED USER')


def contains_telegram_code(input_string):
    pattern = r'\+\d{4,7}$'
    return bool(re.search(pattern, input_string))
