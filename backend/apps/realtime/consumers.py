"""The WebSocket endpoint: every client receives the same stream of ledger facts.

The stream carries facts, never verdicts: appended events, signed checkpoints,
and reconciliation breaks, each with the IDs a client needs to fetch and verify
them through the API.

A slow client never holds up the others or fills the shared channel layer. Each
client has a small buffer drained by its own sender task; when the buffer is full
the oldest facts are dropped so the client stays current, and it's told how many
it missed so it can re-read state over REST. Connections per IP are capped.
"""

import asyncio
from collections import Counter, deque
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from config.env import app_settings

GROUP = "ledger-stream"
TRY_AGAIN_LATER = 1013

_open_per_ip: Counter[str] = Counter()
"""Open connections per client IP in this process."""


class LedgerStreamConsumer(AsyncJsonWebsocketConsumer):
    """Joins the shared group and forwards its messages. Clients only listen."""

    async def connect(self) -> None:
        """Join the stream, unless this IP already has its share of connections."""
        settings = app_settings()
        client = self.scope.get("client") or ("unknown", 0)
        self.ip = str(client[0])
        if _open_per_ip[self.ip] >= settings.ws_max_connections_per_ip:
            self.ip = ""
            await self.close(code=TRY_AGAIN_LATER)
            return
        _open_per_ip[self.ip] += 1
        self.pending: deque[dict[str, Any]] = deque(maxlen=settings.ws_client_buffer)
        self.dropped = 0
        self.ready = asyncio.Event()
        await self.channel_layer.group_add(GROUP, self.channel_name)
        await self.accept()
        self.sender = asyncio.create_task(self._send_pending())

    async def disconnect(self, code: int) -> None:
        """Leave the stream and free this IP's slot."""
        if not getattr(self, "ip", ""):
            return
        self.sender.cancel()
        _open_per_ip[self.ip] -= 1
        if _open_per_ip[self.ip] <= 0:
            del _open_per_ip[self.ip]
        await self.channel_layer.group_discard(GROUP, self.channel_name)

    async def receive_json(self, content: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Ignore anything clients send; the stream is one way."""

    async def ledger_fact(self, message: dict[str, Any]) -> None:
        """Queue one fact for this client, dropping the oldest if it has fallen behind."""
        if len(self.pending) == self.pending.maxlen:
            self.dropped += 1
        self.pending.append(message["fact"])
        self.ready.set()

    async def _send_pending(self) -> None:
        while True:
            await self.ready.wait()
            self.ready.clear()
            if self.dropped:
                missed, self.dropped = self.dropped, 0
                await self.send_json({"kind": "facts_dropped", "count": missed})
            while self.pending:
                await self.send_json(self.pending.popleft())
