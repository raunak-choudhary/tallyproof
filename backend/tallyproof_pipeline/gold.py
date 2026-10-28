"""Silver to gold: conform cleaned contract transactions into ledger events.

Each silver row becomes one validated :class:`~tallyproof_core.events.EventEnvelope`:

- A base award (modification number empty or ``0``) becomes ``obligation.recorded``.
  Any later modification becomes ``obligation.adjusted``; a negative amount there
  is a de-obligation.
- ``occurred_at`` is the action date. ``emitted_at`` is when the government
  reported the transaction, so late reporting shows up as a real gap between the
  two instead of something simulated.
- Event IDs are derived from the transaction key with a seeded generator, so
  rebuilding gold from the same silver gives byte-identical events and the same
  Merkle root.

Gold is written as gzip-compressed JSON Lines in event-time order, ready to be
replayed into Kafka.
"""

import gzip
import hashlib
import json
import random
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

from tallyproof_core.events import EventEnvelope, EventType
from tallyproof_core.ids import new_id

BASE_MODIFICATIONS = frozenset({"", "0", "00", "000"})


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _seeded_rng(key: str, seed: int) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    # Deliberately seeded and non-cryptographic: gold must rebuild byte for byte, and
    # these IDs only need to be unique and reproducible, not unpredictable.
    return random.Random(int.from_bytes(digest[:8], "big"))  # noqa: S311


def conform(row: Mapping[str, object], *, seed: int) -> EventEnvelope:
    """Turn one silver contract transaction into a ledger event.

    Args:
        row: A silver row as a mapping of column name to value.
        seed: Seed that, with the transaction key, fixes the event ID.

    Returns:
        The validated event.

    Raises:
        pydantic.ValidationError: If the row cannot form a valid event.
    """
    key = str(row["contract_transaction_unique_key"])
    action_date = row["action_date"]
    if not isinstance(action_date, date):
        raise TypeError(f"{key}: action_date must be a date, got {action_date!r}")
    reported = row.get("last_modified_date") or row.get("initial_report_date") or action_date
    if not isinstance(reported, date):
        raise TypeError(f"{key}: report dates must be dates")
    occurred_at = _midnight(action_date)
    emitted_at = max(_midnight(reported), occurred_at)
    amount = row["federal_action_obligation"]
    amount_text = f"{Decimal(str(amount)):.2f}" if amount is not None else "0.00"
    modification = _optional(row.get("modification_number")) or ""

    common = {
        "award_key": str(row["contract_award_unique_key"]),
        "amount": amount_text,
        "action_date": action_date.isoformat(),
        "action_type": _optional(row.get("action_type")),
        "description": _optional(row.get("transaction_description")),
    }
    if modification in BASE_MODIFICATIONS:
        event_type = EventType.OBLIGATION_RECORDED
        payload: dict[str, object] = {
            **common,
            "piid": str(row["award_id_piid"]),
            "awarding_agency": str(row["awarding_agency_name"]),
            "funding_agency": _optional(row.get("funding_agency_name")),
            "naics_code": _optional(row.get("naics_code")),
            "psc_code": _optional(row.get("product_or_service_code")),
        }
    else:
        event_type = EventType.OBLIGATION_ADJUSTED
        payload = {**common, "modification_number": modification}

    idempotency_key = f"usaspending:{key}"
    return EventEnvelope.model_validate(
        {
            "event_id": new_id("evt", now=emitted_at, rng=_seeded_rng(key, seed)),
            "idempotency_key": idempotency_key,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "emitted_at": emitted_at,
            "account_id": str(row["recipient_uei"]),
            "correlation_id": hashlib.sha256(idempotency_key.encode()).hexdigest()[:16],
            "payload": {k: v for k, v in payload.items() if v is not None},
        }
    )


def write_events(events: Iterable[EventEnvelope], path: Path) -> int:
    """Write events as gzip-compressed JSON Lines and return how many were written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for event in events:
            handle.write(event.model_dump_json() + "\n")
            count += 1
    return count


def read_events(path: Path) -> Iterator[EventEnvelope]:
    """Read events written by :func:`write_events`, validating each one again."""
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield EventEnvelope.model_validate(json.loads(line))
