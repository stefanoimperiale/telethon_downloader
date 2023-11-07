import asyncio

from telethon import TelegramClient

from env import *
from model.bot_client import BotClient

session = SESSION
user_session = USER_SESSION
download_path_torrent = TG_DOWNLOAD_PATH_TORRENTS  # Directory where to save torrent file (if enabled). Connect with
# torrent client to start download.

client = TelegramClient(session, api_id, api_hash, proxy=None, request_retries=10, flood_sleep_threshold=120, )
user_clients = dict()
last_messages = dict()
current_tasks = dict()

if AUTHORIZED_USER:
    user_clients = dict(
        (int(x), BotClient(TelegramClient(f'{user_session}-{x}', api_id, api_hash, proxy=None, request_retries=10,
                                          flood_sleep_threshold=120), False, int(x))) for x in user_ids)
    last_messages = dict((int(x), None) for x in user_ids)
    current_tasks = dict((int(x), dict()) for x in user_ids)

queue = asyncio.PriorityQueue()
