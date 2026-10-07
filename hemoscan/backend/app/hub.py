"""WebSocket fan-out to dashboards."""
from typing import Set
from fastapi import WebSocket


class Hub:
    def __init__(self):
        self.clients = set()  # type: Set[WebSocket]

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, event: str, data=None):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json({"event": event, "data": data})
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()
