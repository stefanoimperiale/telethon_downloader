# Create a class that hold the last message sent to the user
class LastMessage:
    def __init__(self, user_id, message, operation, arg):
        self.user_id = user_id
        self.message = message
        self.operation = operation
        self.arg = arg
