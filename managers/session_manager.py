from dataclasses import dataclass, field
from asyncio import Queue
from typing import List
import asyncio


@dataclass
class ClientSession:
    session_id: str
    llm_triggered: bool = False
    conversation_history: List[dict] = field(default_factory=list)
    event_queue: Queue = field(default_factory=Queue)


class SessionManager:
    def __init__(self):
        self.sessions = {}

    def create(self, session_id: str):
        session = ClientSession(session_id)
        self.sessions[session_id] = session
        return session

    def get(self, session_id: str):
        return self.sessions.get(session_id)

    def remove(self, session_id: str):
        self.sessions.pop(session_id, None)


session_manager = SessionManager()
