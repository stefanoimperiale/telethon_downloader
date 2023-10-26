import os
import re
from typing import List, Tuple, Any

from telethon.tl.custom import Button

from clients import client
from database import db
from env import PATH_COMPLETED, TG_AUTHORIZED_USER_ID, AUTHORIZED_USER, user_ids
from logger import logger


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


async def tg_send_file(CID, file, name=''):
    async with client.action(CID, 'document') as action:
        await client.send_file(CID, file, caption=name, force_document=True, progress_callback=action.progress)


def get_folders(message_id, message_media_ids, path, is_subscription):
    """ Returns a list of folders in the path """
    folders = []
    for f in os.listdir(path):
        if os.path.isdir(os.path.join(path, f)):
            folders.append((message_id, os.path.join(path, f), f, message_media_ids, is_subscription))
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


async def send_folders_structure(message_to_edit, message_media_ids, base_path=PATH_COMPLETED,
                                 is_subscription=False):
    message_media_id = message_media_ids[-1]
    messages_join = ','.join(message_media_ids)
    dirs = get_folders(message_media_id, messages_join, base_path, is_subscription)
    try:
        with db:
            cur = db.cursor()
            # Insert sub folders
            cur.executemany(
                'INSERT INTO locations(message_id,location,display_location, messages_ids, is_subscription) VALUES ('
                '?, ?, ?, ?, ?)', dirs)
            dirs = cur.execute('SELECT id, display_location FROM locations where message_id=?',
                               (f'{message_media_id}',))
            dirs = sorted(dirs, key=lambda x: x[1])
            buttons = list(
                map(lambda xy: Button.inline(f'{xy[1]}', data=f'{xy[0]}'), dirs))
            buttons = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]  # Max 3 buttons per row

            # Insert current dir
            cur.execute('INSERT INTO locations(message_id,location,display_location, messages_ids, is_subscription) '
                        'VALUES (?, ?, ?, ?, ?)',
                        (message_media_id, base_path, base_path, messages_join, is_subscription))
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
