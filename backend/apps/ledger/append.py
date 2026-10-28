"""Append events to the ledger with gap-free leaf indexes (ADR-0008).

The database is the authority on duplicates: ``idempotency_key`` and the public
event ID are unique. Every append runs inside the caller's transaction and
starts by locking the single ``merkle_log_head`` row, so appends are serialized
and a duplicate check made under the lock cannot race another writer.

Leaf indexes are handed out from that row only after the set of new events is
known, and the row is advanced in the same transaction. If the transaction rolls
back, the row rolls back with it, so the log never skips an index. A database
sequence would leave gaps on rollback.

Batches are sent as arrays and expanded with ``unnest``: one round trip per
statement, and no temporary tables.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from django.db import connection

from tallyproof_core.events import EventEnvelope


class AppendError(RuntimeError):
    """The ledger refused a batch it should have accepted; the transaction must roll back."""


@dataclass(frozen=True)
class Delivery:
    """One event as it arrived from the broker."""

    event: EventEnvelope
    topic: str
    partition: int
    offset: int
    bloom_said_seen: bool = False


@dataclass(frozen=True)
class AppendResult:
    """What one batch did to the log."""

    appended: list[tuple[str, int]]
    """(event ID, leaf index) for each new event, in log order."""
    duplicates: list[Delivery]
    """Deliveries refused because their key or event ID was already in the ledger."""
    tree_size: int
    """Size of the log after this batch."""


_INSERT_EVENTS = """
INSERT INTO ledger_event (public_id, leaf_index, idempotency_key, event_type, account_id,
  occurred_at, emitted_at, canonical_bytes, leaf_hash, kafka_topic, kafka_partition,
  kafka_offset, correlation_id)
SELECT * FROM unnest(%s::text[], %s::bigint[], %s::text[], %s::text[], %s::text[],
  %s::timestamptz[], %s::timestamptz[], %s::bytea[], %s::bytea[], %s::text[], %s::int[],
  %s::bigint[], %s::text[])
ON CONFLICT DO NOTHING
RETURNING public_id, leaf_index
"""

_INSERT_REJECTIONS = """
INSERT INTO dedupe_rejection (idempotency_key, rejected_event_id, kafka_topic, kafka_partition,
  kafka_offset, bloom_said_seen)
SELECT * FROM unnest(%s::text[], %s::text[], %s::text[], %s::int[], %s::bigint[], %s::bool[])
"""


def append(deliveries: Sequence[Delivery]) -> AppendResult:
    """Append a batch in arrival order, refusing duplicates.

    Must be called inside ``transaction.atomic()``; the caller commits the
    consumer offsets in the same transaction.

    Raises:
        AppendError: If called outside a transaction, or if an insert the lock
            should have made safe did not happen.
    """
    if not connection.in_atomic_block:
        raise AppendError("append must run inside transaction.atomic()")
    with connection.cursor() as cursor:
        cursor.execute("SELECT next_leaf_index FROM merkle_log_head WHERE id = 1 FOR UPDATE")
        row = cursor.fetchone()
        if row is None:
            raise AppendError("merkle_log_head has no row; run the migrations")
        head: int = row[0]
        if not deliveries:
            return AppendResult([], [], head)

        keys = [d.event.idempotency_key for d in deliveries]
        ids = [d.event.event_id for d in deliveries]
        cursor.execute(
            "SELECT idempotency_key, public_id FROM ledger_event"
            " WHERE idempotency_key = ANY(%s) OR public_id = ANY(%s)",
            [keys, ids],
        )
        seen_keys: set[str] = set()
        seen_ids: set[str] = set()
        for key, public_id in cursor.fetchall():
            seen_keys.add(key)
            seen_ids.add(public_id)

        fresh: list[Delivery] = []
        duplicates: list[Delivery] = []
        for delivery in deliveries:
            event = delivery.event
            if event.idempotency_key in seen_keys or event.event_id in seen_ids:
                duplicates.append(delivery)
                continue
            seen_keys.add(event.idempotency_key)
            seen_ids.add(event.event_id)
            fresh.append(delivery)

        appended: list[tuple[str, int]] = []
        if fresh:
            events = [d.event for d in fresh]
            cursor.execute(
                _INSERT_EVENTS,
                [
                    [e.event_id for e in events],
                    list(range(head, head + len(fresh))),
                    [e.idempotency_key for e in events],
                    [e.event_type.value for e in events],
                    [e.account_id for e in events],
                    [e.occurred_at for e in events],
                    [e.emitted_at for e in events],
                    [e.canonical_bytes() for e in events],
                    [e.leaf_hash() for e in events],
                    [d.topic for d in fresh],
                    [d.partition for d in fresh],
                    [d.offset for d in fresh],
                    [e.correlation_id for e in events],
                ],
            )
            appended = sorted(cursor.fetchall(), key=lambda r: r[1])
            if len(appended) != len(fresh):
                raise AppendError(
                    f"inserted {len(appended)} of {len(fresh)} new events under the log lock"
                )
            cursor.execute(
                "UPDATE merkle_log_head SET next_leaf_index = %s WHERE id = 1",
                [head + len(fresh)],
            )

        if duplicates:
            cursor.execute(
                _INSERT_REJECTIONS,
                [
                    [d.event.idempotency_key for d in duplicates],
                    [d.event.event_id for d in duplicates],
                    [d.topic for d in duplicates],
                    [d.partition for d in duplicates],
                    [d.offset for d in duplicates],
                    [d.bloom_said_seen for d in duplicates],
                ],
            )
    return AppendResult(appended, duplicates, head + len(fresh))
