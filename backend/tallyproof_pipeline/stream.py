"""Replay gold events into Kafka, in arrival order, at a controlled rate.

This is how the live pipeline gets real data: the same conformed USAspending
events the batch build produced, published to the raw topic as if they were
arriving now. The deliberately invalid records from the overlay are mixed in at
their own arrival times, so the dead-letter path sees real traffic too.

Messages are keyed by award, so every event for one award lands on the same
partition and stays in order. Cash movements have no award and are keyed by
account instead.

Usage::

    python -m tallyproof_pipeline.stream --limit 100000 --rate 2000
"""

import argparse
import gzip
import json
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from tallyproof_core.events import EventEnvelope
from tallyproof_pipeline.gold import read_events
from tallyproof_pipeline.settings import get_settings


class Sink(Protocol):
    """The parts of a Kafka producer the replay uses."""

    def produce(  # noqa: D102
        self,
        topic: str,
        *,
        value: bytes,
        key: bytes,
        on_delivery: Callable[[object, object], None],
    ) -> None: ...
    def poll(self, timeout: float) -> int: ...  # noqa: D102
    def flush(self, timeout: float) -> int: ...  # noqa: D102


class ReplayError(RuntimeError):
    """The broker did not confirm every message."""


@dataclass(frozen=True)
class Outgoing:
    """One message ready to publish."""

    key: bytes
    value: bytes
    valid: bool


@dataclass(frozen=True)
class ReplaySummary:
    """What was published."""

    events: int
    invalid: int
    seconds: float


def partition_key(event: EventEnvelope) -> bytes:
    """Key by award so an award's history stays in order; otherwise by account."""
    award = getattr(event.payload, "award_key", None)
    return (award or event.account_id).encode()


def _emitted(record: dict[str, object]) -> datetime:
    return datetime.fromisoformat(str(record["emitted_at"]))


def interleave(
    events: Iterable[EventEnvelope], invalid: Iterable[dict[str, object]]
) -> Iterator[Outgoing]:
    """Merge invalid records into the event stream at their own arrival times."""
    pending = sorted(invalid, key=_emitted)
    position = 0
    for event in events:
        while position < len(pending) and _emitted(pending[position]) <= event.emitted_at:
            record = pending[position]
            position += 1
            key = str(record.get("account_id") or "invalid").encode()
            yield Outgoing(key, json.dumps(record, sort_keys=True).encode(), valid=False)
        yield Outgoing(partition_key(event), event.model_dump_json().encode(), valid=True)
    for record in pending[position:]:
        key = str(record.get("account_id") or "invalid").encode()
        yield Outgoing(key, json.dumps(record, sort_keys=True).encode(), valid=False)


def publish(
    messages: Iterable[Outgoing],
    sink: Sink,
    topic: str,
    rate_per_sec: int,
    limit: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> ReplaySummary:
    """Publish messages at no more than ``rate_per_sec``, then wait for every confirmation.

    Raises:
        ReplayError: If the broker rejected any message or didn't confirm them all.
    """
    failures: list[object] = []

    def on_delivery(error: object, message: object) -> None:
        if error is not None:
            failures.append(error)

    started = clock()
    events = invalid = 0
    for sent, message in enumerate(messages):
        if limit is not None and events >= limit:
            break
        # Pace against the start time, so short stalls are caught up smoothly.
        ahead = started + sent / rate_per_sec - clock()
        if ahead > 0:
            sleep(ahead)
        sink.produce(topic, value=message.value, key=message.key, on_delivery=on_delivery)
        sink.poll(0)
        if message.valid:
            events += 1
        else:
            invalid += 1
    unconfirmed = sink.flush(60.0)
    if unconfirmed or failures:
        raise ReplayError(
            f"{unconfirmed} messages unconfirmed and {len(failures)} rejected; first: "
            f"{failures[0] if failures else 'none'}"
        )
    return ReplaySummary(events, invalid, clock() - started)


def read_invalid(path: Path) -> list[dict[str, object]]:
    """Read the overlay's deliberately invalid records, if the gold build wrote any."""
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Replay the gold events into the raw topic."""
    from confluent_kafka import Producer

    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=settings.replay_slice_events)
    parser.add_argument("--rate", type=int, default=settings.replay_rate_per_sec)
    args = parser.parse_args()
    producer = Producer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "acks": "all",
            "enable.idempotence": True,
            "linger.ms": 20,
            "compression.type": "lz4",
        }
    )
    gold = settings.gold_dir
    summary = publish(
        interleave(
            read_events(gold / "events.jsonl.gz"), read_invalid(gold / "invalid_records.jsonl.gz")
        ),
        producer,
        settings.kafka_topic_events_raw,
        args.rate,
        args.limit,
    )
    print(
        f"published {summary.events} events and {summary.invalid} invalid records "
        f"in {summary.seconds:.1f} s"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
