"""Turn messages from the ledger's Kafka topics into stream facts."""

import json
from typing import Any

from channels.layers import get_channel_layer

from apps.realtime.consumers import GROUP

KINDS = {
    "ledger.appended": "event_appended",
    "ledger.checkpoints": "checkpoint_signed",
    "recon.breaks": "break_found",
}


def to_fact(topic: str, value: bytes | None) -> dict[str, Any] | None:
    """The fact a topic message announces, or None for topics the stream doesn't carry."""
    kind = next((name for prefix, name in KINDS.items() if topic.startswith(prefix)), None)
    if kind is None or not value:
        return None
    return {"kind": kind, **json.loads(value)}


async def broadcast(facts: list[dict[str, Any]]) -> None:
    """Send facts to every connected client.

    Call this from one long-lived event loop: the Redis channel layer keeps a
    connection pool per loop, so a new loop per message would open a new
    connection per message and run the machine out of local ports.
    """
    layer = get_channel_layer()
    if layer is None:
        return
    for fact in facts:
        await layer.group_send(GROUP, {"type": "ledger.fact", "fact": fact})
