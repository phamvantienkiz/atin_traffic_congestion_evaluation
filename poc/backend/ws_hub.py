"""WebSocket hub and 5 Hz broadcast loop."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WsHub:
    """Manages connected WebSocket clients and broadcasts JSON payloads."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, msg: dict) -> None:
        if not self.clients:
            return
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                self.disconnect(ws)


async def push_loop(engine, hub: WsHub, events, store, hz: float = 5.0) -> None:
    interval = 1.0 / hz if hz > 0 else 0.2
    while True:
        try:
            await hub.broadcast({"type": "results", "data": engine.latest_results()})
            for partial, frame in engine.pop_events():
                cam = store.get(partial["camera_id"])
                ev = await asyncio.to_thread(events.add, partial, frame, cam)
                await hub.broadcast({"type": "event", "data": ev})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error in WebSocket push_loop")
        await asyncio.sleep(interval)
