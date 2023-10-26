# Create a class that hold the telethon client and the auth state
class BotClient:
    def __init__(self, client, authenticated, user_id):
        self._client = client
        self._authenticated = authenticated
        self._user_id = user_id
        self._phone = None

    def get_client(self):
        return self._client

    def get_user_id(self):
        return self._user_id

    def get_phone(self):
        return self._phone

    def is_authenticated(self):
        return self._authenticated

    def set_authenticated(self, authenticated):
        self._authenticated = authenticated

    def set_phone(self, phone):
        self._phone = phone
