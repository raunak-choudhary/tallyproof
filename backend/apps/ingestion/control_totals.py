"""Control totals: does the ledger account for every message on the raw topic?

For one partition and offset range, every message must end up exactly one way:
appended to the ledger, refused as a duplicate, or (if invalid) dead-lettered.
Beyond counting, each appended row's leaf hash is recomputed from its source
message, so a stored row that no longer matches the stream is caught, and the
amounts on both sides are summed.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import connection
from pydantic import ValidationError

from tallyproof_core.events import EventEnvelope


@dataclass
class ControlReport:
    """The outcome for one partition range."""

    partition: int
    messages: int = 0
    invalid: int = 0
    appended: int = 0
    duplicates: int = 0
    stream_amount: Decimal = Decimal(0)
    ledger_amount: Decimal = Decimal(0)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when every message is accounted for and nothing differs."""
        return not self.problems


def _amount(event: EventEnvelope) -> Decimal:
    payload = event.payload.model_dump(mode="json")
    return Decimal(payload.get("amount") or payload.get("period_outlay") or 0)


def reconcile_range(
    topic: str, partition: int, messages: dict[int, bytes | None], start: int, end: int
) -> ControlReport:
    """Compare messages at offsets ``[start, end)`` with what the ledger recorded for them."""
    report = ControlReport(partition)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT kafka_offset, leaf_hash FROM ledger_event"
            " WHERE kafka_topic = %s AND kafka_partition = %s"
            " AND kafka_offset >= %s AND kafka_offset < %s",
            [topic, partition, start, end],
        )
        stored = {int(offset): bytes(leaf) for offset, leaf in cursor.fetchall()}
        cursor.execute(
            "SELECT kafka_offset FROM dedupe_rejection"
            " WHERE kafka_topic = %s AND kafka_partition = %s"
            " AND kafka_offset >= %s AND kafka_offset < %s",
            [topic, partition, start, end],
        )
        refused = {int(row[0]) for row in cursor.fetchall()}
    for offset in range(start, end):
        if offset not in messages:
            continue  # compacted or not yet read; nothing to compare
        report.messages += 1
        try:
            event = EventEnvelope.model_validate_json(messages[offset] or b"")
        except (ValidationError, ValueError):
            report.invalid += 1
            if offset in stored:
                report.problems.append(
                    f"offset {offset} is invalid on the stream but in the ledger"
                )
            continue
        report.stream_amount += _amount(event)
        if offset in stored:
            report.appended += 1
            report.ledger_amount += _amount(event)
            if stored[offset] != event.leaf_hash():
                report.problems.append(f"offset {offset}: ledger row does not match its message")
        elif offset in refused:
            report.duplicates += 1
            report.ledger_amount += _amount(event)
        else:
            report.problems.append(f"offset {offset} was neither appended nor refused")
    if report.stream_amount != report.ledger_amount:
        report.problems.append(
            f"amounts differ: stream {report.stream_amount}, ledger {report.ledger_amount}"
        )
    return report
