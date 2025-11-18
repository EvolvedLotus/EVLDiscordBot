"""Shared state between bot and backend - avoids circular imports"""

class SharedState:
    def __init__(self):
        self.bot = None
        self.data_manager = None
        self.supabase_client = None

    def set_bot(self, bot):
        self.bot = bot

    def set_data_manager(self, dm):
        self.data_manager = dm

    def set_supabase(self, client):
        self.supabase_client = client

# Global instance
state = SharedState()
