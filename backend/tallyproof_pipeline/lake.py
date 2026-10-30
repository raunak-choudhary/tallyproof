"""Sink the event stream into Iceberg tables, exactly once, and prove the lake is complete.

The sink reads the same stream the replay publishes to Kafka: gold events in log
order, with the overlay's invalid records mixed in at their arrival times. Every
message ends exactly one way, as it does in ingestion:

- **appended** to ``tallyproof.events``, partitioned by event type and month;
- **refused** as a duplicate of an idempotency key already in the lake;
- **dead-lettered** to ``tallyproof.dead_letters`` if it fails validation.

Duplicates are found the way the ledger finds them. A Bloom filter predicts: a
"new" answer is always right, so most keys skip any lookup. A "maybe seen" answer
is checked exactly against the table, which is the authority, the way the
database's unique constraint is for the ledger (ADR-0008).

Each commit records how far into the stream it got as a property of the Iceberg
snapshot, written atomically with the rows. A rerun resumes from there, so the
sink can be stopped at any point and never writes a row twice.

Each lake row keeps the event's exact canonical bytes and leaf hash, so a row can
be checked against the ledger's inclusion proofs. The catalog is a local SQLite
file and the warehouse a local folder; on AWS they would be the Glue Data Catalog
and S3, with the same table layout (``docs/limitations.md``).

Usage::

    python -m tallyproof_pipeline.lake sink      # make lake
    python -m tallyproof_pipeline.lake check     # make lake-check
"""

import argparse
import json
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from tallyproof_core.bloom import BloomFilter
from tallyproof_core.events import EventEnvelope
from tallyproof_core.hashing import leaf_hash
from tallyproof_pipeline.gold import read_events
from tallyproof_pipeline.stream import interleave, read_invalid

if TYPE_CHECKING:
    import pyarrow as pa
    from pyiceberg.catalog import Catalog
    from pyiceberg.table import Table

NAMESPACE = "tallyproof"
EVENTS = f"{NAMESPACE}.events"
DEAD_LETTERS = f"{NAMESPACE}.dead_letters"
POSITION = "tallyproof.source-position"
"""Snapshot property: how many stream messages the lake has accounted for."""
AMOUNT_SCALE = 2


@dataclass(frozen=True)
class Message:
    """One message of the stream, at its position."""

    position: int
    raw: bytes


@dataclass
class TypeTotal:
    """Count and exact sum of one event type."""

    count: int = 0
    amount: Decimal = Decimal(0)


@dataclass
class Batch:
    """What one slice of the stream does to the lake."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    dead: list[dict[str, Any]] = field(default_factory=list)
    duplicates: int = 0
    maybe_seen: int = 0
    false_positives: int = 0
    end: int = 0
    """Position just after the last message in the batch."""


@dataclass
class Totals:
    """Counts and sums on one side of the control-total comparison."""

    messages: int = 0
    appended: int = 0
    duplicates: int = 0
    invalid: int = 0
    by_type: dict[str, TypeTotal] = field(default_factory=dict)

    def add(self, event_type: str, amount: Decimal | None) -> None:
        """Count one appended event."""
        total = self.by_type.setdefault(event_type, TypeTotal())
        total.count += 1
        total.amount += amount or Decimal(0)


def amount_of(event: EventEnvelope) -> Decimal | None:
    """The money an event moves: an obligation's amount or a period's outlay."""
    payload = event.payload.model_dump(mode="json")
    value = payload.get("amount")
    if value is None:
        value = payload.get("period_outlay")
    return None if value is None else Decimal(str(value))


def stream(events: Path, invalid: Path, start: int = 0) -> Iterator[Message]:
    """The replay's stream from ``start``: valid events and invalid records, in arrival order."""
    for position, outgoing in enumerate(interleave(read_events(events), read_invalid(invalid))):
        if position >= start:
            yield Message(position, outgoing.value)


def row_of(event: EventEnvelope, position: int) -> dict[str, Any]:
    """The lake row for an event. The canonical bytes are the ones the ledger hashes."""
    award = getattr(event.payload, "award_key", None)
    return {
        "event_id": event.event_id,
        "idempotency_key": event.idempotency_key,
        "event_type": event.event_type.value,
        "account_id": event.account_id,
        "award_key": award,
        "occurred_at": event.occurred_at,
        "emitted_at": event.emitted_at,
        "amount": amount_of(event),
        "canonical": event.canonical_bytes().decode(),
        "leaf_hash": event.leaf_hash().hex(),
        "correlation_id": event.correlation_id,
        "source_position": position,
    }


def classify(
    messages: Sequence[Message], bloom: BloomFilter, existing: Callable[[set[str]], set[str]]
) -> Batch:
    """Sort a slice of the stream into rows to append, duplicates, and dead letters.

    ``existing`` returns which of the given keys the lake already holds; it is asked
    only about keys the Bloom filter can't rule out. Keys accepted here are added to
    the filter, so the next slice sees them.
    """
    batch = Batch(end=messages[-1].position + 1 if messages else 0)
    parsed: list[tuple[EventEnvelope, int]] = []
    for message in messages:
        try:
            event = EventEnvelope.model_validate_json(message.raw)
        except (ValidationError, ValueError) as error:
            batch.dead.append(dead_letter(message, error))
            continue
        parsed.append((event, message.position))

    candidates = {
        e.idempotency_key for e, _ in parsed if bloom.might_contain(e.idempotency_key.encode())
    }
    batch.maybe_seen = len(candidates)
    held = existing(candidates) if candidates else set()
    batch.false_positives = len(candidates - held)

    seen_here: set[str] = set()
    for event, position in parsed:
        key = event.idempotency_key
        if key in held or key in seen_here:
            batch.duplicates += 1
            continue
        seen_here.add(key)
        batch.rows.append(row_of(event, position))
    for key in seen_here:
        bloom.add(key.encode())
    return batch


def dead_letter(message: Message, error: Exception) -> dict[str, Any]:
    """A dead-letter row: the raw record and why it was refused, without the record's values."""
    if isinstance(error, ValidationError):
        reason = "; ".join(
            f"{'.'.join(str(p) for p in issue['loc'])}: {issue['type']}" for issue in error.errors()
        )
    else:
        reason = type(error).__name__
    return {"source_position": message.position, "reason": reason, "raw": message.raw.decode()}


def compare(source: Totals, lake: Totals, expected_valid: int | None) -> list[str]:
    """Every difference between what the stream holds and what the lake holds."""
    problems = []
    if lake.messages != source.messages:
        problems.append(
            f"lake accounts for {lake.messages} messages; the stream has {source.messages}"
        )
    for name in ("appended", "invalid"):
        if getattr(lake, name) != getattr(source, name):
            problems.append(f"{name}: lake {getattr(lake, name)}, stream {getattr(source, name)}")
    for event_type in sorted(source.by_type.keys() | lake.by_type.keys()):
        s = source.by_type.get(event_type, TypeTotal())
        k = lake.by_type.get(event_type, TypeTotal())
        if s.count != k.count:
            problems.append(f"{event_type}: lake has {k.count} events, stream {s.count}")
        if s.amount != k.amount:
            problems.append(f"{event_type}: lake sums to {k.amount}, stream to {s.amount}")
    if expected_valid is not None and source.appended + source.duplicates != expected_valid:
        problems.append(
            f"the stream has {source.appended + source.duplicates} valid events;"
            f" the gold build reported {expected_valid}"
        )
    return problems


def source_totals(messages: Iterable[Message]) -> Totals:
    """Totals of the stream itself, with first-seen-wins deduplication by idempotency key."""
    totals = Totals()
    seen: set[str] = set()
    for message in messages:
        totals.messages += 1
        try:
            event = EventEnvelope.model_validate_json(message.raw)
        except (ValidationError, ValueError):
            totals.invalid += 1
            continue
        if event.idempotency_key in seen:
            totals.duplicates += 1
            continue
        seen.add(event.idempotency_key)
        totals.appended += 1
        totals.add(event.event_type.value, amount_of(event))
    return totals


# Iceberg tables. Everything below needs pyiceberg and a catalog; the unit tests run
# it against a catalog in a temporary folder.


def _schemas() -> tuple[Any, Any, Any]:
    from pyiceberg.partitioning import PartitionField, PartitionSpec
    from pyiceberg.schema import Schema
    from pyiceberg.transforms import IdentityTransform, MonthTransform
    from pyiceberg.types import (
        DecimalType,
        LongType,
        NestedField,
        StringType,
        TimestamptzType,
    )

    events = Schema(
        NestedField(1, "event_id", StringType(), required=True),
        NestedField(2, "idempotency_key", StringType(), required=True),
        NestedField(3, "event_type", StringType(), required=True),
        NestedField(4, "account_id", StringType(), required=True),
        NestedField(5, "award_key", StringType(), required=False),
        NestedField(6, "occurred_at", TimestamptzType(), required=True),
        NestedField(7, "emitted_at", TimestamptzType(), required=True),
        NestedField(8, "amount", DecimalType(38, AMOUNT_SCALE), required=False),
        NestedField(9, "canonical", StringType(), required=True, doc="RFC 8785 bytes, hashed"),
        NestedField(10, "leaf_hash", StringType(), required=True, doc="RFC 9162 leaf hash, hex"),
        NestedField(11, "correlation_id", StringType(), required=True),
        NestedField(12, "source_position", LongType(), required=True),
    )
    spec = PartitionSpec(
        PartitionField(3, 1000, IdentityTransform(), "event_type"),
        PartitionField(6, 1001, MonthTransform(), "occurred_month"),
    )
    dead = Schema(
        NestedField(1, "source_position", LongType(), required=True),
        NestedField(2, "reason", StringType(), required=True),
        NestedField(3, "raw", StringType(), required=True),
    )
    return events, spec, dead


def open_catalog(uri: str, warehouse: Path) -> "Catalog":
    """The SQL catalog, creating the namespace and both tables on first use."""
    from pyiceberg.catalog.sql import SqlCatalog

    warehouse.mkdir(parents=True, exist_ok=True)
    catalog = SqlCatalog(NAMESPACE, uri=uri, warehouse=warehouse.resolve().as_uri())
    catalog.create_namespace_if_not_exists(NAMESPACE)
    events, spec, dead = _schemas()
    catalog.create_table_if_not_exists(EVENTS, schema=events, partition_spec=spec)
    catalog.create_table_if_not_exists(DEAD_LETTERS, schema=dead)
    return catalog


def position(table: "Table") -> int:
    """How far into the stream the table's latest snapshot got; zero when empty."""
    snapshot = table.current_snapshot()
    if snapshot is None or snapshot.summary is None:
        return 0
    return int(snapshot.summary.additional_properties.get(POSITION, 0))


def _arrow(rows: list[dict[str, Any]], schema: Any) -> "pa.Table":  # noqa: ANN401
    import pyarrow as pa

    return pa.Table.from_pylist(rows, schema=schema.as_arrow())


def keys_in(table: "Table", keys: set[str]) -> set[str]:
    """Which of ``keys`` the events table already holds."""
    from pyiceberg.expressions import In

    if table.current_snapshot() is None or not keys:
        return set()
    found = table.scan(
        row_filter=In(term="idempotency_key", literals=keys), selected_fields=("idempotency_key",)
    )
    return {str(k) for k in found.to_arrow().column("idempotency_key").to_pylist()}


def load_bloom(table: "Table", expected: int, fpr: float) -> BloomFilter:
    """A filter holding every idempotency key already in the lake."""
    bloom = BloomFilter.for_capacity(expected, fpr)
    if table.current_snapshot() is not None:
        keys = table.scan(selected_fields=("idempotency_key",)).to_arrow().column("idempotency_key")
        for key in keys.to_pylist():
            bloom.add(str(key).encode())
    return bloom


@dataclass
class SinkReport:
    """What one sink run did."""

    started_at_position: int = 0
    ended_at_position: int = 0
    commits: int = 0
    appended: int = 0
    duplicates: int = 0
    dead_lettered: int = 0
    bloom_maybe_seen: int = 0
    bloom_false_positives: int = 0


def sink(
    catalog: "Catalog",
    messages_from: Callable[[int], Iterator[Message]],
    batch_rows: int,
    bloom_items: int,
    bloom_fpr: float,
    on_commit: Callable[[SinkReport], None] = lambda _: None,
) -> SinkReport:
    """Append the stream to the lake from where the last run stopped."""
    events_table = catalog.load_table(EVENTS)
    dead_table = catalog.load_table(DEAD_LETTERS)
    events_schema, _, dead_schema = _schemas()
    start = position(events_table)
    report = SinkReport(started_at_position=start, ended_at_position=start)
    bloom = load_bloom(events_table, bloom_items, bloom_fpr)
    already_dead = _dead_positions(dead_table)

    pending: list[Message] = []

    def flush() -> None:
        if not pending:
            return
        batch = classify(pending, bloom, lambda keys: keys_in(events_table, keys))
        dead = [d for d in batch.dead if d["source_position"] not in already_dead]
        if dead:
            # Written first: if the run stops before the events commit, the rerun
            # skips these positions instead of writing them twice.
            dead_table.append(_arrow(dead, dead_schema))
            already_dead.update(d["source_position"] for d in dead)
        # The position commits with the rows, so the two can never disagree.
        events_table.append(
            _arrow(batch.rows, events_schema), snapshot_properties={POSITION: str(batch.end)}
        )
        report.commits += 1
        report.appended += len(batch.rows)
        report.duplicates += batch.duplicates
        report.dead_lettered += len(batch.dead)
        report.bloom_maybe_seen += batch.maybe_seen
        report.bloom_false_positives += batch.false_positives
        report.ended_at_position = batch.end
        pending.clear()
        on_commit(report)

    for message in messages_from(start):
        pending.append(message)
        if len(pending) >= batch_rows:
            flush()
    flush()
    return report


def _dead_positions(table: "Table") -> set[int]:
    if table.current_snapshot() is None:
        return set()
    column = table.scan(selected_fields=("source_position",)).to_arrow().column("source_position")
    return {int(p) for p in column.to_pylist()}


def lake_totals(catalog: "Catalog") -> tuple[Totals, list[str]]:
    """Totals read back from the tables, and any row that fails its own checks.

    The table is read in record batches, so memory stays flat. Every row's leaf hash
    is recomputed from its stored canonical bytes, and event IDs and idempotency keys
    must each be unique.
    """
    events_table = catalog.load_table(EVENTS)
    totals = Totals(messages=position(events_table))
    problems: list[str] = []
    ids: set[str] = set()
    keys: set[str] = set()
    repeated = mismatched = 0
    if events_table.current_snapshot() is not None:
        reader = events_table.scan(
            selected_fields=(
                "event_id",
                "idempotency_key",
                "event_type",
                "amount",
                "canonical",
                "leaf_hash",
            )
        ).to_arrow_batch_reader()
        for batch in reader:
            columns = batch.to_pydict()
            for event_id, key, event_type, amount, canonical, leaf in zip(
                columns["event_id"],
                columns["idempotency_key"],
                columns["event_type"],
                columns["amount"],
                columns["canonical"],
                columns["leaf_hash"],
                strict=True,
            ):
                totals.appended += 1
                totals.add(event_type, amount)
                if event_id in ids or key in keys:
                    repeated += 1
                ids.add(event_id)
                keys.add(key)
                if leaf_hash(canonical.encode()).hex() != leaf:
                    mismatched += 1
    if repeated:
        problems.append(f"{repeated} rows repeat an event ID or idempotency key")
    if mismatched:
        problems.append(f"{mismatched} rows whose leaf hash doesn't match their canonical bytes")
    dead_table = catalog.load_table(DEAD_LETTERS)
    if dead_table.current_snapshot() is not None:
        totals.invalid = dead_table.scan(selected_fields=("source_position",)).to_arrow().num_rows
    totals.duplicates = totals.messages - totals.appended - totals.invalid
    return totals, problems


def snapshots(table: "Table") -> list[dict[str, Any]]:
    """The table's history: one entry per commit, newest last."""
    out = []
    for snapshot in table.snapshots():
        summary = snapshot.summary.additional_properties if snapshot.summary else {}
        out.append(
            {
                "snapshot_id": snapshot.snapshot_id,
                "position": int(summary.get(POSITION, 0)),
                "added_records": int(summary.get("added-records", 0)),
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - exercised by make lake
    """Run the sink or the control-total check."""
    from tallyproof_pipeline.settings import get_settings

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("sink", "check"))
    args = parser.parse_args(argv)
    settings = get_settings()
    gold = settings.gold_dir
    events_file, invalid_file = gold / "events.jsonl.gz", gold / "invalid_records.jsonl.gz"
    catalog = open_catalog(settings.lake_catalog_uri, settings.lake_dir / "warehouse")
    reports = settings.lake_dir / "_reports"
    reports.mkdir(parents=True, exist_ok=True)

    if args.command == "sink":

        def progress(r: SinkReport) -> None:
            print(
                f"commit {r.commits}: position {r.ended_at_position:,}, appended {r.appended:,},"
                f" duplicates {r.duplicates}, dead letters {r.dead_lettered}",
                flush=True,
            )

        result = sink(
            catalog,
            lambda start: stream(events_file, invalid_file, start),
            settings.lake_batch_rows,
            settings.lake_bloom_expected_items,
            settings.lake_bloom_target_fpr,
            progress,
        )
        (reports / "sink.json").write_text(json.dumps(asdict(result), indent=2) + "\n")
        print(json.dumps(asdict(result), indent=2))
        return 0

    gold_report = (
        json.loads((gold / "report.json").read_text()) if (gold / "report.json").exists() else {}
    )
    expected = (
        gold_report["real_events"] + gold_report["outlay_events"] + gold_report["injected_events"]
        if gold_report
        else None
    )
    source = source_totals(stream(events_file, invalid_file))
    lake, problems = lake_totals(catalog)
    problems += compare(source, lake, expected)
    outcome = {
        "ok": not problems,
        "problems": problems,
        "source": asdict(source),
        "lake": asdict(lake),
        "gold_report_valid_events": expected,
        "snapshots": len(snapshots(catalog.load_table(EVENTS))),
    }
    (reports / "control_totals.json").write_text(json.dumps(outcome, indent=2, default=str) + "\n")
    print(json.dumps(outcome, indent=2, default=str))
    return 0 if not problems else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
