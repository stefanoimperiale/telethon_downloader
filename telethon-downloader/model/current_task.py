# Create a class that hold the current downloading task info
import os
import sys

sys.path.append("..")
from clients import client


class CurrentTask:
    def __init__(self, task, message, file_path):
        self.task = task
        self.message = message
        self.file_path = file_path

    async def cancel(self, message=None):
        self.task.cancel(message)
        if message == 'CANCEL':
            await client.edit_message(self.message[1][0], '❌ Download cancelled')
            if os.path.exists(self.file_path):
                os.unlink(self.file_path)
