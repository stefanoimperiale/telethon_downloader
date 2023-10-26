# Create a class that hold the telethon client and the auth state
class Subscription:
    def __init__(self, user_id, chat_id, location, display_name):
        self.user_id = user_id
        self.chat_id = chat_id
        self.location = location
        self.display_name = display_name
