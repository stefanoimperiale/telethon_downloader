import os
from typing import Type, Tuple, List

from logger import logger


def get_env(name, message, cast: Type[str | bool | int] = str):
    if name in os.environ:
        logger.info(f'{name} : {os.environ[name]}')
        return cast(os.environ[name].strip())
    else:
        logger.info(f'{name} : {message}')
        return message


# Define some variables so the code reads easier
api_id = get_env('TG_API_ID', 'Enter your API ID: ', int)
api_hash = get_env('TG_API_HASH', 'Enter your API hash: ')
bot_token = get_env('TG_BOT_TOKEN', 'Enter your Telegram BOT token: ')

TG_AUTHORIZED_USER_ID = get_env('TG_AUTHORIZED_USER_ID', False)
TG_CONFIG_PATH = get_env('TG_CONFIG_PATH', '/config')
TG_DOWNLOAD_PATH = get_env('TG_DOWNLOAD_PATH', '/download')
TG_DOWNLOAD_PATH_TORRENTS = get_env('TG_DOWNLOAD_PATH_TORRENTS', '/watch')
YOUTUBE_LINKS_SOPORTED = get_env('YOUTUBE_LINKS_SUPPORTED', 'youtube.com,youtu.be')
YOUTUBE_FORMAT = get_env('YOUTUBE_FORMAT', 'bestvideo+bestaudio/best')  # best
TG_UNZIP_TORRENTS = get_env('TG_UNZIP_TORRENTS', False)
TG_PROGRESS_DOWNLOAD = get_env('TG_PROGRESS_DOWNLOAD', True)
TG_ALLOWED_PHOTO = get_env('TG_ALLOWED_PHOTO', False)

TG_MAX_PARALLEL = int(os.environ.get('TG_MAX_PARALLEL', 4))
TG_DL_TIMEOUT = int(os.environ.get('TG_DL_TIMEOUT', 7200))
YT_DL_TIMEOUT = int(os.environ.get('TG_DL_TIMEOUT', 7200))

TG_SQLITE_FILE = os.path.join(TG_CONFIG_PATH, 'bottorrent.db')
SESSION = os.path.join(TG_CONFIG_PATH, 'bottorrent')
USER_SESSION = os.path.join(TG_CONFIG_PATH, 'userbot')

PATH_TMP = os.path.join(TG_DOWNLOAD_PATH)
PATH_COMPLETED = os.path.join(TG_DOWNLOAD_PATH)

PATH_YOUTUBE = os.path.join(TG_DOWNLOAD_PATH, 'youtube')

VERSION = "VERSION 4.1.1"
HELP = """
/help		: This Screen
/subscribe  : Subscribe to a channel or a group and download a new media file as soon as it is posted
/version	: Version  
/download	: Download files or folder inside your mapped download directory

/id			: YOUR ID TELEGRAM
"""

REQUEST_CHAT_ID = 22


def get_users() -> Tuple[bool, List[int]]:
    """ Returns a list of inputted strings """
    inputs = []
    if not TG_AUTHORIZED_USER_ID:
        return False, inputs
    elif TG_AUTHORIZED_USER_ID.strip() == '':
        return False, inputs
    else:
        inputs = list(map(int, TG_AUTHORIZED_USER_ID.strip().replace(" ", "").replace('-100', '').split(',')))
        return True, inputs


AUTHORIZED_USER, user_ids = get_users()
