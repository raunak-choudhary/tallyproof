"""Derived views that read the log in leaf order: the journal, reconciliation, the outbox.

Each projection keeps a cursor, the next leaf index it will read, in
``projection_cursor``. A step locks the cursor, reads the next events, applies
them, and advances the cursor in the same transaction. A crash rolls back both,
so a projection never skips or repeats an event, and it can be rebuilt from the
log alone.
"""

import json
import logging
from collections.abc import Sequence
from typing import Protocol

from django.db import DatabaseError, connection, transaction

from apps.ledger.models import JournalLine, LedgerEvent, Outbox
from tallyproof_core.events import EventEnvelope
from tallyproof_core.journal import entry_for

log = logging.getLogger(__name__)

OUTBOX_CHANNEL = "outbox_ready"
"""Postgres notification channel that wakes the outbox relay."""


def envelope_of(row: LedgerEvent) -> EventEnvelope:
    """Rebuild a stored event's envelope from the exact bytes that were hashed."""
    document = json.loads(bytes(row.canonical_bytes))
    return EventEnvelope.model_validate({**document, "correlation_id": row.correlation_id or "-"})


class Projection(Protocol):
    """A view derived from events in log order."""

    name: str

    def apply(self, events: Sequence[LedgerEvent]) -> None:
        """Derive rows for these events, inside the caller's transaction."""


def step(projection: Projection, batch_size: int = 500) -> int:
    """Apply the next batch of events to a projection. Returns how many were read."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO projection_cursor (name, next_leaf_index) VALUES (%s, 0)"
                " ON CONFLICT (name) DO NOTHING",
                [projection.name],
            )
            cursor.execute(
                "SELECT next_leaf_index FROM projection_cursor WHERE name = %s FOR UPDATE",
                [projection.name],
            )
            start: int = cursor.fetchone()[0]
        events = list(
            LedgerEvent.objects.filter(
                leaf_index__gte=start, leaf_index__lt=start + batch_size
            ).order_by("leaf_index")
        )
        if not events:
            return 0
        if events[0].leaf_index != start or events[-1].leaf_index != start + len(events) - 1:
            raise RuntimeError(f"{projection.name}: the log has a gap after leaf {start}")
        projection.apply(events)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE projection_cursor SET next_leaf_index = %s, updated_at = now()"
                " WHERE name = %s",
                [start + len(events), projection.name],
            )
            # Delivered only on commit; wakes the relay if this step wrote outbox rows.
            cursor.execute("SELECT pg_notify(%s, %s)", [OUTBOX_CHANNEL, projection.name])
    return len(events)


def run_round(projections: Sequence[Projection], batch_size: int = 500) -> int:
    """Step each projection once. Returns how many events they read in all.

    Each step is its own transaction, so a projection that fails leaves nothing
    half-written, and the others keep going while it is retried next round.
    """
    read = 0
    for projection in projections:
        try:
            read += step(projection, batch_size)
        except DatabaseError:
            log.exception("projection %s failed; retrying on the next round", projection.name)
    return read


def catch_up(projection: Projection, batch_size: int = 500) -> int:
    """Apply every event not yet projected. Returns how many were read."""
    total = 0
    while read := step(projection, batch_size):
        total += read
    return total


class JournalProjection:
    """Posts the double-entry journal (ADR-0013)."""

    name = "journal"

    def apply(self, events: Sequence[LedgerEvent]) -> None:
        """Insert each event's balanced lines."""
        lines = []
        for row in events:
            entry_id = f"jrn:{row.public_id}"
            for number, line in enumerate(entry_for(envelope_of(row)), start=1):
                lines.append(
                    JournalLine(
                        event=row,
                        leaf_index=row.leaf_index,
                        entry_id=entry_id,
                        line_number=number,
                        account=line.account.value,
                        debit=line.debit,
                        credit=line.credit,
                    )
                )
        JournalLine.objects.bulk_create(lines)


class AppendedProjection:
    """Announces every appended event on ``ledger.appended`` through the outbox."""

    name = "appended"

    def __init__(self, topic: str) -> None:
        """Publish to ``topic``."""
        self.topic = topic

    def apply(self, events: Sequence[LedgerEvent]) -> None:
        """Write one outbox message per event, keyed by account."""
        Outbox.objects.bulk_create(
            Outbox(
                topic=self.topic,
                key=row.account_id,
                payload={
                    "event_id": row.public_id,
                    "leaf_index": row.leaf_index,
                    "event_type": row.event_type,
                    "account_id": row.account_id,
                    "leaf_hash_hex": bytes(row.leaf_hash).hex(),
                },
            )
            for row in events
        )
