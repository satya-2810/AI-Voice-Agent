from typing import Dict
import logging

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self):
        self.chat_histories: Dict[str, list] = {}

    def add_message(self, session_id: str, role: str, content: str):
        if session_id not in self.chat_histories:
            self.chat_histories[session_id] = []

        self.chat_histories[session_id].append(
            {
                "role": role,
                "content": content,
            }
        )

    def get_recent_messages(self, session_id: str, limit: int = 10):
        return self.chat_histories.get(session_id, [])[-limit:]

    def clear_session(self, session_id: str):
        self.chat_histories.pop(session_id, None)

    def get_session_count(self):
        return len(self.chat_histories)
