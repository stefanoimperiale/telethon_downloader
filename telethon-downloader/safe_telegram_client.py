from clients import client
import time
from logger import logger
from telethon.errors import FloodWaitError

async def safe_edit_message(messageId, text):
    try:
        await client.edit_message(messageId, text)
    except FloodWaitError as e:
        logger.warn(f"Flood wait error: Need to wait for {e.seconds} seconds")
        time.sleep(e.seconds)
        await safe_edit_message(messageId, text)

async def safe_send_message(userId, text, buttons=None):
    try:
        await client.send_message(userId, text, buttons)
    except FloodWaitError as e:
        logger.warn(f"Flood wait error: Need to wait for {e.seconds} seconds")
        time.sleep(e.seconds)
        await safe_send_message(userId, text, buttons)