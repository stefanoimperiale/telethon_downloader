# Create a class that hold the current downloading task info
import os
import sys
sys.path.append("..")
from clients import client


class CurrentTask:
    def __init__(self, task, message, file_path, prev_status):
        self.task = task
        self.message = message
        self.file_path = file_path
        self.prev_status = prev_status

    async def cancel(self, message=None):
        self.task.cancel(message)
        if self.prev_status == 'PAUSE':
            await client.edit_message(self.message[0], '❌ Download cancelled')
            if os.path.exists(self.file_path):
                os.unlink(self.file_path)
        if message == 'PAUSE':
            self.prev_status = 'PAUSE'
