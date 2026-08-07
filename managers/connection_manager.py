from fastapi import WebSocket
from typing import Dict
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"Client connected: {session_id}")

    def disconnect(self, session_id: str):
        self.active_connections.pop(session_id, None)
        logger.info(f"Client disconnected: {session_id}")

    def get(self, session_id: str):
        return self.active_connections.get(session_id)

    async def send_json(self, session_id: str, payload: dict):
        websocket = self.get(session_id)

        if websocket:
            await websocket.send_text(json.dumps(payload))


manager = ConnectionManager()
