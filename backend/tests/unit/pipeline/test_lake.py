"""The Iceberg sink: every message ends one way, reruns resume, and the totals agree.

The sink tests run the real pyiceberg code against a SQLite catalog and a warehouse
in a temporary folder, so they need no containers.
"""

import gzip
from collections.abc import Callable, Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from pyiceberg.catalog import Catalog

from tallyproof_core.bloom import BloomFilter
from tallyproof_core.events import EventEnvelope
from tallyproof_pipeline.lake import (
    EVENTS,
    Message,
    SinkReport,
    Totals,
    TypeTotal,
    classify,
    compare,
    lake_totals,
    open_catalog,
    position,
    row_of,
    sink,
    snapshots,
    source_totals,
)
from tallyproof_pipeline.settings import REPO_ROOT

SAMPLE = REPO_ROOT / "testdata" / "sample" / "gold_events_sample.jsonl.gz"
INVALID = b'{"event_id": "evt_bad", "payload": {"amount": 1250.5}}'


def sample_lines(count: int) -> list[bytes]:
    with gzip.open(SAMPLE, "rb") as handle:
        return [next(handle).strip() for _ in range(count)]


@pytest.fixture
def stream_messages() -> list[Message]:
    """300 real events, two of them delivered twice, and two invalid records."""
    lines = sample_lines(300)
    raw = [*lines[:100], INVALID, lines[10], *lines[100:200], lines[150], INVALID, *lines[200:]]
    return [Message(n, r) for n, r in enumerate(raw)]


def from_list(messages: list[Message]) -> Callable[[int], Iterator[Message]]:
    return lambda start: iter(messages[start:])


@pytest.fixture
def catalog(tmp_path: Path) -> Catalog:
    return open_catalog(f"sqlite:///{tmp_path / 'catalog.db'}", tmp_path / "warehouse")


def run(catalog: Catalog, messages: list[Message], batch: int = 64) -> SinkReport:
    return sink(catalog, from_list(messages), batch, 10_000, 0.001)


# The pure parts.


def test_classify_sorts_messages_three_ways() -> None:
    lines = sample_lines(3)
    messages = [
        Message(0, lines[0]),
        Message(1, INVALID),
        Message(2, lines[0]),
        Message(3, lines[1]),
    ]
    batch = classify(messages, BloomFilter.for_capacity(100, 0.01), lambda keys: set())
    assert [r["source_position"] for r in batch.rows] == [0, 3]
    assert batch.duplicates == 1
    assert [d["source_position"] for d in batch.dead] == [1]
    assert batch.end == 4


def test_classify_asks_the_table_only_about_keys_the_filter_cannot_rule_out() -> None:
    lines = sample_lines(2)
    held = EventEnvelope.model_validate_json(lines[0]).idempotency_key
    bloom = BloomFilter.for_capacity(100, 0.01)
    bloom.add(held.encode())
    asked: list[set[str]] = []

    def existing(keys: set[str]) -> set[str]:
        asked.append(keys)
        return keys & {held}

    batch = classify([Message(0, lines[0]), Message(1, lines[1])], bloom, existing)
    assert asked == [{held}]
    assert batch.duplicates == 1
    assert batch.maybe_seen == 1
    assert batch.false_positives == 0
    assert len(batch.rows) == 1


def test_classify_counts_a_false_positive_and_appends_the_event() -> None:
    line = sample_lines(1)[0]
    key = EventEnvelope.model_validate_json(line).idempotency_key
    bloom = BloomFilter.for_capacity(100, 0.01)
    bloom.add(key.encode())  # the filter thinks it has seen the key; the table hasn't
    batch = classify([Message(0, line)], bloom, lambda keys: set())
    assert (batch.false_positives, len(batch.rows)) == (1, 1)


def test_classify_adds_accepted_keys_to_the_filter() -> None:
    line = sample_lines(1)[0]
    bloom = BloomFilter.for_capacity(100, 0.01)
    classify([Message(0, line)], bloom, lambda keys: set())
    assert bloom.might_contain(EventEnvelope.model_validate_json(line).idempotency_key.encode())


def test_dead_letters_name_the_field_without_quoting_its_value() -> None:
    batch = classify([Message(7, INVALID)], BloomFilter.for_capacity(10, 0.01), lambda k: set())
    (dead,) = batch.dead
    assert dead["source_position"] == 7
    assert "payload" in dead["reason"]
    assert "1250.5" not in dead["reason"]


def test_row_keeps_the_bytes_the_ledger_hashes() -> None:
    event = EventEnvelope.model_validate_json(sample_lines(1)[0])
    row = row_of(event, 5)
    assert row["canonical"].encode() == event.canonical_bytes()
    assert row["leaf_hash"] == event.leaf_hash().hex()
    assert row["source_position"] == 5


def test_source_totals_keep_the_first_of_each_key(stream_messages: list[Message]) -> None:
    totals = source_totals(stream_messages)
    assert (totals.messages, totals.appended, totals.duplicates, totals.invalid) == (
        304,
        300,
        2,
        2,
    )
    assert sum(t.count for t in totals.by_type.values()) == 300


def test_compare_finds_nothing_when_both_sides_agree() -> None:
    side = Totals(10, 8, 1, 1, {"a": TypeTotal(8, Decimal("1.50"))})
    other = Totals(10, 8, 1, 1, {"a": TypeTotal(8, Decimal("1.50"))})
    assert compare(side, other, expected_valid=9) == []


def test_compare_names_each_difference() -> None:
    source = Totals(10, 8, 1, 1, {"a": TypeTotal(8, Decimal("1.50"))})
    lake = Totals(9, 7, 1, 1, {"a": TypeTotal(7, Decimal("1.49"))})
    problems = compare(source, lake, expected_valid=12)
    assert any("9 messages" in p for p in problems)
    assert any(p.startswith("appended") for p in problems)
    assert any("7 events" in p for p in problems)
    assert any("1.49" in p for p in problems)
    assert any("gold build reported 12" in p for p in problems)


# The sink, on a real catalog in a temporary folder.


def test_sink_accounts_for_every_message(catalog: Catalog, stream_messages: list[Message]) -> None:
    report = run(catalog, stream_messages)
    assert (report.appended, report.duplicates, report.dead_lettered) == (300, 2, 2)
    assert report.ended_at_position == 304
    lake, problems = lake_totals(catalog)
    assert problems == []
    assert compare(source_totals(stream_messages), lake, expected_valid=302) == []


def test_a_rerun_appends_nothing(catalog: Catalog, stream_messages: list[Message]) -> None:
    run(catalog, stream_messages)
    again = run(catalog, stream_messages)
    assert again.started_at_position == 304
    assert again.appended == 0
    assert lake_totals(catalog)[0].appended == 300


def test_a_stopped_run_resumes_without_writing_twice(
    catalog: Catalog, stream_messages: list[Message]
) -> None:
    class StopRunError(Exception):
        pass

    def stops_after(count: int) -> Callable[[int], Iterator[Message]]:
        def messages(start: int) -> Iterator[Message]:
            for message in stream_messages[start:]:
                if message.position >= count:
                    raise StopRunError
                yield message

        return messages

    with pytest.raises(StopRunError):
        sink(catalog, stops_after(150), 64, 10_000, 0.001)
    assert position(catalog.load_table(EVENTS)) == 128  # two full batches committed
    report = run(catalog, stream_messages)
    assert report.started_at_position == 128
    lake, problems = lake_totals(catalog)
    assert problems == []
    assert compare(source_totals(stream_messages), lake, expected_valid=302) == []


def test_every_commit_records_its_position(
    catalog: Catalog, stream_messages: list[Message]
) -> None:
    run(catalog, stream_messages)
    history = snapshots(catalog.load_table(EVENTS))
    assert [h["position"] for h in history] == [64, 128, 192, 256, 304]
    assert sum(h["added_records"] for h in history) == 300
