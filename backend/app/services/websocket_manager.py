from fastapi import WebSocket
from typing import List, Dict, Any
import json


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] 客户端连接，当前在线: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WS] 客户端断开，当前在线: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return

        message_str = json.dumps(message, ensure_ascii=False)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                print(f"[WS] 发送失败: {e}")
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def send_progress(self, data: Dict[str, Any]):
        await self.broadcast({
            "type": "progress",
            "data": data
        })

    async def send_completed(self, data: Dict[str, Any]):
        await self.broadcast({
            "type": "completed",
            "data": data
        })

    async def send_error(self, error_msg: str):
        await self.broadcast({
            "type": "error",
            "data": {"message": error_msg}
        })


ws_manager = WebSocketManager()
