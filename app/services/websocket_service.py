from fastapi import WebSocket
from typing import Dict, Set
import asyncio

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()
        if username not in self.active_connections:
            self.active_connections[username] = set()
        self.active_connections[username].add(websocket)

    async def disconnect(self, websocket: WebSocket, username: str):
        if username in self.active_connections:
            self.active_connections[username].remove(websocket)

    async def notify_new_email(self, username: str):
        if username in self.active_connections:
            for connection in self.active_connections[username]:
                try:
                    await connection.send_json({"type": "new_email"})
                except:
                    continue

websocket_manager = WebSocketManager()