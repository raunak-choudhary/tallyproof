"""Reconciliation in SQL agrees with the streaming rules, break for break."""

import duckdb
import pytest

from evals.dataset import OUT_DIR
from tallyproof_pipeline.batch_recon import GOLD_RULES, batch_gold, compare, streaming_gold

EVENTS = OUT_DIR / "events.jsonl.gz"


@pytest.fixture(scope="module")
def comparison() -> dict[str, dict[str, int]]:
    return compare(batch_gold(duckdb.connect(), EVENTS), streaming_gold(EVENTS))


@pytest.mark.parametrize("rule", sorted(GOLD_RULES))
def test_batch_and_streaming_find_the_same_breaks(
    comparison: dict[str, dict[str, int]], rule: str
) -> None:
    result = comparison[rule]
    assert result["batch"] > 0, "every rule has labelled cases in the evaluation dataset"
    assert (result["only_batch"], result["only_streaming"]) == (0, 0)


def test_compare_counts_each_side() -> None:
    result = compare({"orphan_outlay": {"a", "b"}}, {"orphan_outlay": {"b", "c"}})
    assert result["orphan_outlay"] == {
        "batch": 2,
        "streaming": 2,
        "both": 1,
        "only_batch": 1,
        "only_streaming": 1,
    }


def test_the_silver_rules_find_one_of_each_on_a_tiny_table() -> None:
    from tallyproof_pipeline.batch_recon import SILVER_RULES

    rows = [
        # Two new awards with the same recipient, amount, and date: one duplicate.
        ("U1", "0", "100.00", "2024-01-05", "2024-01-05 09:00", "A1", "T1"),
        ("U1", "0", "100.00", "2024-01-05", "2024-01-05 09:30", "A2", "T2"),
        # An award de-obligated below zero.
        ("U2", "0", "50.00", "2024-02-01", "2024-02-01 08:00", "A3", "T3"),
        ("U2", "P1", "-80.00", "2024-03-01", "2024-03-01 08:00", "A3", "T4"),
        # Eight new awards to a quiet recipient within an hour.
        *[
            (
                "U3",
                "0",
                f"{10 + k}.00",
                "2024-04-01",
                f"2024-04-01 10:{5 * k:02d}",
                f"B{k}",
                f"S{k}",
            )
            for k in range(8)
        ],
    ]
    con = duckdb.connect(config={"threads": 1})
    con.execute(
        "CREATE TABLE silver (recipient_uei VARCHAR, modification_number VARCHAR,"
        " federal_action_obligation DECIMAL(19, 2), action_date DATE,"
        " initial_report_date TIMESTAMP, contract_award_unique_key VARCHAR,"
        " contract_transaction_unique_key VARCHAR)"
    )
    con.executemany("INSERT INTO silver VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    counts = {rule: con.execute(sql).fetchone()[0] for rule, sql in SILVER_RULES.items()}  # type: ignore[index]
    assert counts == {
        "possible_duplicate_award": 1,
        "deobligation_exceeds_award": 1,
        "recipient_burst": 1,
    }
