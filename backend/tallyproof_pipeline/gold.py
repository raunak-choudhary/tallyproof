"""Silver to gold: conform cleaned contract transactions into ledger events.

Usage::

    python -m tallyproof_pipeline.gold

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
import heapq
import json
import random
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

from pyspark.sql import DataFrame
from pyspark.sql import functions as F  # noqa: N812 - conventional alias

from tallyproof_core.events import EventEnvelope, EventType
from tallyproof_core.ids import new_id
from tallyproof_pipeline.overlay import arrival_key, plan, positive_totals, write_labels
from tallyproof_pipeline.settings import PipelineSettings, get_settings
from tallyproof_pipeline.silver import spark_session

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
    if isinstance(reported, datetime):
        # Silver stores report times as UTC wall-clock time without a zone.
        reported_at = reported if reported.tzinfo else reported.replace(tzinfo=UTC)
    elif isinstance(reported, date):
        reported_at = _midnight(reported)
    else:
        raise TypeError(f"{key}: report dates must be dates or timestamps")
    occurred_at = _midnight(action_date)
    emitted_at = max(reported_at, occurred_at)
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


@dataclass(frozen=True)
class GoldReport:
    """What the gold build produced."""

    real_events: int
    injected_events: int
    invalid_records: int
    rows_rejected: int


SLICE_COLUMNS = (
    "contract_transaction_unique_key",
    "contract_award_unique_key",
    "award_id_piid",
    "modification_number",
    "federal_action_obligation",
    "action_date",
    "last_modified_date",
    "initial_report_date",
    "awarding_agency_name",
    "funding_agency_name",
    "recipient_uei",
    "transaction_description",
    "action_type",
    "naics_code",
    "product_or_service_code",
)
"""The silver columns :func:`conform` reads. Selecting only these keeps rows narrow."""

POOL_SIZE = 5000
"""Real events kept in memory as the pool the anomaly overlay copies from."""


class GoldOrderError(RuntimeError):
    """Raised if Spark's ordering and the events' arrival order ever disagree."""


def replay_slice(silver: DataFrame, limit: int) -> DataFrame:
    """Pick the first ``limit`` transactions by action date, sorted in arrival order.

    A plain sort-then-limit makes Spark hold every selected row in memory at once,
    which ran out of heap at a million rows. Instead, per-day counts (one small row
    per day) give the cutoff day; rows before it are filtered, and only the cutoff
    day itself is sorted and trimmed. The slice is then sorted by arrival with a
    disk-backed shuffle, using the same emission formula as :func:`conform`.
    """
    counts = silver.groupBy("action_date").count().orderBy("action_date").collect()
    before, cutoff = 0, None
    for row in counts:
        if before + row["count"] >= limit:
            cutoff = row["action_date"]
            break
        before += row["count"]
    if cutoff is None:
        sliced = silver
    else:
        boundary_day = (
            silver.where(F.col("action_date") == F.lit(cutoff))
            .orderBy("contract_transaction_unique_key")
            .limit(limit - before)
        )
        sliced = silver.where(F.col("action_date") < F.lit(cutoff)).unionByName(boundary_day)
    occurred = F.to_timestamp_ntz(F.date_format(F.col("action_date"), "yyyy-MM-dd HH:mm:ss"))
    reported = F.coalesce(F.col("last_modified_date"), F.col("initial_report_date"), occurred)
    return (
        sliced.select(*SLICE_COLUMNS)
        .withColumn("_emitted", F.greatest(reported, occurred))
        .orderBy("_emitted", "contract_transaction_unique_key")
    )


def build_gold(settings: PipelineSettings, silver: DataFrame) -> GoldReport:
    """Conform a slice of silver into events, add the overlay, and write gold.

    Memory stays flat however large the slice is: rows stream to the driver one
    partition at a time and each event is written as soon as it is conformed. The
    overlay plans its anomalies from a seeded reservoir sample of real events and
    per-award totals, then they are merged into the stream in arrival order. Rows
    that cannot form a valid event are counted, not hidden.
    """
    gold = settings.gold_dir
    gold.mkdir(parents=True, exist_ok=True)
    base_path = gold / "_base.jsonl.gz"
    sampler = _seeded_rng("reservoir", settings.overlay_seed)
    pool: list[EventEnvelope] = []
    totals: dict[str, Decimal] = defaultdict(Decimal)
    real = rejected = recorded_seen = 0
    previous: tuple[object, str] | None = None
    with gzip.open(base_path, "wt", encoding="utf-8") as out:
        for row in replay_slice(silver, settings.replay_slice_events).toLocalIterator():
            try:
                event = conform(row.asDict(), seed=settings.overlay_seed)
            except (TypeError, ValueError):
                rejected += 1
                continue
            key = arrival_key(event)
            if previous is not None and key < previous:
                raise GoldOrderError(f"{event.idempotency_key} arrived out of order")
            previous = key
            out.write(event.model_dump_json() + "\n")
            real += 1
            for award, amount in positive_totals([event]).items():
                totals[award] += amount
            if event.event_type is EventType.OBLIGATION_RECORDED:
                recorded_seen += 1
                if len(pool) < POOL_SIZE:
                    pool.append(event)
                elif (slot := sampler.randrange(recorded_seen)) < POOL_SIZE:
                    pool[slot] = event

    planned = plan(
        pool, totals, seed=settings.overlay_seed, per_anomaly=settings.overlay_per_anomaly
    )
    merged = heapq.merge(read_events(base_path), planned.injected, key=arrival_key)
    written = write_events(merged, gold / "events.jsonl.gz")
    base_path.unlink()
    write_labels(planned.labels, gold / "labels.jsonl")
    with gzip.open(gold / "invalid_records.jsonl.gz", "wt", encoding="utf-8") as handle:
        for record in planned.invalid_records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    report = GoldReport(
        real_events=real,
        injected_events=written - real,
        invalid_records=len(planned.invalid_records),
        rows_rejected=rejected,
    )
    (gold / "report.json").write_text(json.dumps(asdict(report), indent=2) + "\n")
    return report


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Build gold from silver and print a summary."""
    settings = get_settings()
    spark = spark_session(settings)
    try:
        silver = spark.read.parquet(str(settings.silver_dir / "contracts"))
        print(build_gold(settings, silver))
    finally:
        spark.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
