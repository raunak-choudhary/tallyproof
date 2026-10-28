"""Publish outbox messages to Kafka (the transactional outbox pattern).

Derived facts are written to ``outbox`` in the same transaction as the change
that caused them, so a fact is never published for a change that rolled back,
and never lost for one that committed. The relay publishes unpublished rows in
order and marks them published only after the broker confirms every one.

Delivery is at least once: if the relay stops between the broker's confirmation
and the database update, those rows are sent again. Every message carries its
outbox ID in the ``outbox-id`` header so consumers can drop repeats.
"""

import json
from collections.abc import Callable
from typing import Protocol

from django.db import connection, transaction

from apps.ledger.models import Outbox


class Sink(Protocol):
    """The parts of a Kafka producer the relay uses."""

    def produce(  # noqa: D102
        self,
        topic: str,
        *,
        value: bytes,
        key: bytes,
        headers: list[tuple[str, str | bytes | None]],
        on_delivery: Callable[[object, object], None],
    ) -> None: ...
    def flush(self, timeout: float) -> int: ...  # noqa: D102


class RelayError(RuntimeError):
    """The broker did not confirm a batch; nothing was marked published."""


def relay_batch(sink: Sink, limit: int = 500, flush_timeout: float = 30.0) -> int:
    """Publish the oldest unpublished messages. Returns how many were published."""
    failures: list[object] = []

    def on_delivery(error: object, message: object) -> None:
        if error is not None:
            failures.append(error)

    with transaction.atomic():
        # SKIP LOCKED lets a second relay take the next batch instead of waiting.
        batch = list(
            Outbox.objects.select_for_update(skip_locked=True)
            .filter(published_at__isnull=True)
            .order_by("id")[:limit]
        )
        if not batch:
            return 0
        for message in batch:
            sink.produce(
                message.topic,
                value=json.dumps(message.payload, sort_keys=True).encode(),
                key=message.key.encode(),
                headers=[("outbox-id", str(message.pk).encode())],
                on_delivery=on_delivery,
            )
        unconfirmed = sink.flush(flush_timeout)
        if unconfirmed or failures:
            raise RelayError(f"{unconfirmed} unconfirmed and {len(failures)} rejected messages")
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE outbox SET published_at = now() WHERE id = ANY(%s)",
                [[message.pk for message in batch]],
            )
    return len(batch)
