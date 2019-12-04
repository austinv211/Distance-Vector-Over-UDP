class Message:
    """
    used as a datastore for message content
    """
    def __init__(self, update_fields, sender_port, sender_id, sender_ip):
        self.num_updates = len(update_fields)
        self.update_fields = update_fields
        self.sender_port = sender_port
        self.sender_ip = sender_ip

    def __str__(self):
        return f'{self.update_fields}'