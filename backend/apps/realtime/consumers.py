"""The WebSocket endpoint: every client receives the same stream of ledger facts.

The stream carries facts, never verdicts: appended events, signed checkpoints,
and reconciliation breaks, each with the IDs a client needs to fetch and verify
them through the API.
"""

from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer

GROUP = "ledger-stream"


class LedgerStreamConsumer(AsyncJsonWebsocketConsumer):
    """Joins the shared group and forwards its messages. Clients only listen."""

    async def connect(self) -> None:
        """Join the stream."""
        await self.channel_layer.group_add(GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        """Leave the stream."""
        await self.channel_layer.group_discard(GROUP, self.channel_name)

    async def receive_json(self, content: Any, **kwargs: Any) -> None:  # noqa: ANN401
        """Ignore anything clients send; the stream is one way."""

    async def ledger_fact(self, message: dict[str, Any]) -> None:
        """Forward one fact to this client."""
        await self.send_json(message["fact"])
