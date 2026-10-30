"""The load test's arithmetic: percentiles, clock correction, pacing, and the report."""

import gzip
import json
from pathlib import Path

import pytest

from tallyproof_pipeline.load_test import (
    Distribution,
    Drain,
    Paced,
    Report,
    clock_offset,
    distribution,
    drain_rate,
    latencies,
    markdown,
    paced_rate,
    read_messages,
    take,
)
from tallyproof_pipeline.settings import REPO_ROOT

SAMPLE = REPO_ROOT / "testdata" / "sample" / "gold_events_sample.jsonl.gz"


def test_distribution_uses_nearest_rank() -> None:
    d = distribution([float(n) for n in range(1, 101)])
    assert (d.count, d.p50, d.p95, d.p99, d.max) == (100, 50.0, 95.0, 99.0, 100.0)


def test_distribution_of_one_value_is_that_value() -> None:
    assert distribution([7.0]) == Distribution(1, 7.0, 7.0, 7.0, 7.0)


def test_distribution_of_nothing_is_zero() -> None:
    assert distribution([]) == Distribution(0, 0.0, 0.0, 0.0, 0.0)


def test_clock_offset_trusts_the_shortest_round_trip() -> None:
    # Database clock is 2.5 s ahead. The slow sample would suggest 2.0 s.
    samples = [(100.0, 103.5, 102.0), (200.0, 202.55, 200.1)]
    assert clock_offset(samples) == pytest.approx(2.5)


def test_drain_rate_leaves_the_last_batch_out_of_the_span() -> None:
    # 1,000 events; the last batch of 200 shares the final stamp, 4 s after the first.
    assert drain_rate(1_000, 200, 4.0) == (5.0, 200.0)


def test_drain_rate_of_a_single_batch_is_unknown() -> None:
    assert drain_rate(500, 500, 0.0) == (0.0, 0.0)


@pytest.mark.parametrize(
    ("ceiling", "share", "expected"),
    [(2_345.0, 0.5, 1_100), (150.0, 0.5, 100), (10_000.0, 0.25, 2_500)],
)
def test_paced_rate_rounds_down_to_hundreds(ceiling: float, share: float, expected: int) -> None:
    assert paced_rate(ceiling, share) == expected


def test_latencies_correct_for_the_clock_and_skip_gaps() -> None:
    sent = {"evt_a": 10.0, "evt_b": 11.0}
    reached = [("evt_a", 12.1), ("evt_b", None), ("evt_c", 13.0)]
    assert latencies(sent, reached, offset=2.0) == [pytest.approx(100.0)]


def test_read_messages_keys_by_award_and_keeps_order(tmp_path: Path) -> None:
    messages = take(read_messages(SAMPLE), 5)
    with gzip.open(SAMPLE, "rt", encoding="utf-8") as handle:
        first = [json.loads(next(handle)) for _ in range(5)]
    assert [m.event_id for m in messages] == [e["event_id"] for e in first]
    assert all(m.key for m in messages)
    assert json.loads(messages[0].value)["event_id"] == first[0]["event_id"]


def test_take_stops_when_the_source_runs_out() -> None:
    assert len(take(iter(take(read_messages(SAMPLE), 3)), 10)) == 3


def test_markdown_has_every_section() -> None:
    lag = Distribution(10, 5.0, 9.0, 12.0, 20.0)
    report = Report(
        started_at="2026-10-30 15:00 UTC",
        hardware={"CPU": "Apple M3, 8 cores"},
        settings={"Raw topic partitions": "3"},
        drains=[Drain(1, 30_000, 12.5, 2_400.0, lag)],
        paced=Paced(1_200, 15_000, 1, lag, lag, lag, lag),
        proofs=lag,
        proof_tree_size=105_000,
        partitions={"raw[0]": 35_000},
    )
    text = markdown(report)
    assert "| 1 | 30,000 | 12.5 | 2,400 | 5 | 9 | 12 | 20 |" in text
    assert "steady 1,200 events per second" in text
    assert "covered by a signed checkpoint" in text
    assert "log of 105,000 leaves" in text
    assert "| raw[0] | 35,000 |" in text


def test_markdown_leaves_out_what_was_not_measured() -> None:
    text = markdown(Report(started_at="t", hardware={}, settings={}))
    assert "Throughput" not in text
    assert "Inclusion proofs" not in text
