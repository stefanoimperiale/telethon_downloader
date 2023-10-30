from telethon.sync import TelegramClient
from env import *

id_user = input('Enter your ID: ')

user_session = USER_SESSION

user_client = TelegramClient(f'{user_session}-{id_user}', api_id, api_hash, proxy=None, request_retries=10,
                             flood_sleep_threshold=120)

with user_client:
    logger.info(f'User {id_user} authenticated')
