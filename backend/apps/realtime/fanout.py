"""Turn messages from the ledger's Kafka topics into stream facts."""

import json
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import structlog
from channels.layers import get_channel_layer

from apps.realtime.consumers import GROUP

log = structlog.get_logger(__name__)
BATCH = 200


class Message(Protocol):
    """The parts of a Kafka message the fan-out reads."""

    def topic(self) -> str | None: ...  # noqa: D102
    def value(self) -> bytes | None: ...  # noqa: D102
    def offset(self) -> int | None: ...  # noqa: D102
    def error(self) -> object | None: ...  # noqa: D102


class Source(Protocol):
    """Where messages come from: a Kafka consumer, or a fake one in tests."""

    def consume(self, num_messages: int, timeout: float) -> Sequence[Message]: ...  # noqa: D102


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
    body = json.loads(value)
    if not isinstance(body, dict):
        raise ValueError("a fact is a JSON object")
    return {"kind": kind, **body}


def facts_in(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """The facts a batch announces.

    Errors, other topics, and unreadable values are skipped, so one bad message
    can't stop the stream.
    """
    facts = []
    for message in messages:
        topic = message.topic()
        if message.error() is not None or topic is None:
            continue
        try:
            fact = to_fact(topic, message.value())
        except ValueError:
            log.warning("skipping an unreadable message", topic=topic, offset=message.offset())
            continue
        if fact is not None:
            facts.append(fact)
    return facts


async def pump(source: Source, should_stop: Callable[[], bool]) -> None:
    """Read batches and broadcast their facts until ``should_stop`` returns true."""
    while not should_stop():
        facts = facts_in(source.consume(num_messages=BATCH, timeout=1.0))
        if facts:
            await broadcast(facts)


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
