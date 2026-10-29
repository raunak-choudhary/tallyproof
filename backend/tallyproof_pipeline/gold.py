"""Silver to gold: conform cleaned contract transactions into ledger events.

Usage::

    python -m tallyproof_pipeline.gold

Each silver row becomes one validated :class:`~tallyproof_core.events.EventEnvelope`:

- A base award (modification number empty or ``0``) becomes ``obligation.recorded``.
  Any later modification becomes ``obligation.adjusted``; a negative amount there
  is a de-obligation.
- ``occurred_at`` is the action date. ``emitted_at`` is when the government
  first reported the transaction, so late reporting shows up as a real gap between the
  two instead of something simulated.
- Each award in the replayed slice also gets an ``outlay.reported`` event for every
  period it was paid in, from the outlay silver table when it has been built. An
  outlay event is the agency's report, so it is stamped with when the report was
  made; the period it covers is in the payload.
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

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F  # noqa: N812 - conventional alias

from tallyproof_core.contact_data import remove_contact_data
from tallyproof_core.events import EventEnvelope, EventType
from tallyproof_core.ids import new_id
from tallyproof_pipeline.outlay_silver import reported_at
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
    # The first report, not the last edit: records are edited for years afterwards,
    # and an edit time would make old transactions look reported late.
    reported = row.get("initial_report_date") or row.get("last_modified_date") or action_date
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
        "description": remove_contact_data(_optional(row.get("transaction_description"))),
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


def conform_outlay(row: Mapping[str, object], *, recipient: str, seed: int) -> EventEnvelope:
    """Turn one outlay silver row into an ``outlay.reported`` event.

    Args:
        row: A row of the outlay silver table.
        recipient: The award's recipient UEI, taken from its contract transactions.
        seed: Seed that, with the outlay's key, fixes the event ID.
    """
    award, account = str(row["award_key"]), str(row["treasury_account"])
    fiscal_year, period = int(str(row["fiscal_year"])), int(str(row["fiscal_period"]))
    reported = row.get("reported_at")
    if reported is not None and not isinstance(reported, datetime):
        raise TypeError(f"{award}: reported_at must be a timestamp, got {reported!r}")
    at = reported_at(reported, fiscal_year, period)
    idempotency_key = f"usaspending:outlay:{award}:{account}:FY{fiscal_year}P{period:02d}"
    return EventEnvelope.model_validate(
        {
            "event_id": new_id("evt", now=at, rng=_seeded_rng(idempotency_key, seed)),
            "idempotency_key": idempotency_key,
            "event_type": EventType.OUTLAY_REPORTED,
            "occurred_at": at,
            "emitted_at": at,
            "account_id": recipient,
            "correlation_id": hashlib.sha256(idempotency_key.encode()).hexdigest()[:16],
            "payload": {
                "award_key": award,
                "treasury_account": account,
                "fiscal_year": fiscal_year,
                "fiscal_period": period,
                "cumulative_outlay": f"{Decimal(str(row['cumulative_outlay'])):.2f}",
                "period_outlay": f"{Decimal(str(row['period_outlay'])):.2f}",
            },
        }
    )


def slice_outlays(
    spark: SparkSession, settings: PipelineSettings, recipients: Mapping[str, str]
) -> DataFrame | None:
    """Outlay silver rows for the awards in the replayed slice, sorted in arrival order.

    Returns None when outlay silver hasn't been built. The sort uses the same
    emission time and idempotency key as :func:`conform_outlay`, so the rows can be
    streamed straight into the merge without holding them in memory.
    """
    path = settings.silver_dir / "outlays"
    if not path.exists() or not recipients:
        return None
    awards = spark.createDataFrame([(award,) for award in recipients], ["award_key"])
    month = (F.col("fiscal_period") + 8) % 12 + 1
    year = F.col("fiscal_year") - F.when(month >= 10, 1).otherwise(0)
    period_end = F.to_timestamp_ntz(
        F.date_format(F.last_day(F.make_date(year, month, F.lit(1))), "yyyy-MM-dd HH:mm:ss")
    )
    key = F.format_string(
        "usaspending:outlay:%s:%s:FY%dP%02d",
        "award_key",
        "treasury_account",
        "fiscal_year",
        "fiscal_period",
    )
    return (
        spark.read.parquet(str(path))
        .join(F.broadcast(awards), "award_key", "left_semi")
        .withColumn("_emitted", F.coalesce(F.col("reported_at"), period_end))
        .withColumn("_key", key)
        .orderBy("_emitted", "_key")
    )


def stream_outlays(
    rows: DataFrame, recipients: Mapping[str, str], seed: int
) -> Iterator[EventEnvelope]:
    """Conform sorted outlay rows one at a time, checking the order as they pass."""
    previous: tuple[object, str] | None = None
    for row in rows.toLocalIterator():
        event = conform_outlay(row.asDict(), recipient=recipients[row["award_key"]], seed=seed)
        key = arrival_key(event)
        if previous is not None and key < previous:
            raise GoldOrderError(f"{event.idempotency_key} arrived out of order")
        previous = key
        yield event


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
    outlay_events: int
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

POOL_OUTLAYS = 50
"""Real outlays offered to the overlay, so injected outlays borrow real accounts."""


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
    reported = F.coalesce(F.col("initial_report_date"), F.col("last_modified_date"), occurred)
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
    recipients: dict[str, str] = {}
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
            award_key = getattr(event.payload, "award_key", None)
            if award_key is not None:
                recipients.setdefault(award_key, event.account_id)
            for award, amount in positive_totals([event]).items():
                totals[award] += amount
            if event.event_type is EventType.OBLIGATION_RECORDED:
                recorded_seen += 1
                if len(pool) < POOL_SIZE:
                    pool.append(event)
                elif (slot := sampler.randrange(recorded_seen)) < POOL_SIZE:
                    pool[slot] = event

    outlay_rows = slice_outlays(silver.sparkSession, settings, recipients)
    seed = settings.overlay_seed
    # A few real outlays in the pool let injected outlays use real Treasury accounts.
    sample = (
        []
        if outlay_rows is None
        else [
            conform_outlay(row.asDict(), recipient=recipients[row["award_key"]], seed=seed)
            for row in outlay_rows.limit(POOL_OUTLAYS).collect()
        ]
    )
    planned = plan([*pool, *sample], totals, seed=seed, per_anomaly=settings.overlay_per_anomaly)
    outlays = iter(()) if outlay_rows is None else stream_outlays(outlay_rows, recipients, seed)
    outlay_count = 0

    def counted(events: Iterator[EventEnvelope]) -> Iterator[EventEnvelope]:
        nonlocal outlay_count
        for event in events:
            outlay_count += 1
            yield event

    merged = heapq.merge(
        read_events(base_path), counted(outlays), planned.injected, key=arrival_key
    )
    written = write_events(merged, gold / "events.jsonl.gz")
    base_path.unlink()
    write_labels(planned.labels, gold / "labels.jsonl")
    with gzip.open(gold / "invalid_records.jsonl.gz", "wt", encoding="utf-8") as handle:
        for record in planned.invalid_records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    report = GoldReport(
        real_events=real,
        outlay_events=outlay_count,
        injected_events=written - real - outlay_count,
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
