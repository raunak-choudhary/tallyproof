"""Every provable total over the evaluation dataset equals the oracle's independent sum.

The oracle computes expected answers from the labelled data without the analyst's
code. If the sum tree groups a record differently from the analyst's views, a proven
total would disagree with the oracle here.
"""

import gzip
import json
from decimal import Decimal

import pytest

from evals.dataset import OUT_DIR as EVAL_DIR
from evals.oracle import Oracle
from tallyproof_core.events import EventEnvelope
from tallyproof_core.sum_tree import SumTree, verify_total
from tallyproof_core.totals import OBLIGATIONS, OUTLAYS, Record, leaves, prefix


@pytest.fixture(scope="module")
def tree_and_oracle() -> tuple[SumTree, bytes, Oracle]:
    records: list[Record] = []
    seen: set[str] = set()
    with gzip.open(EVAL_DIR / "events.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            event = EventEnvelope.model_validate(json.loads(line))
            if event.idempotency_key in seen:
                continue  # the ledger refuses a repeated delivery; so does the oracle
            seen.add(event.idempotency_key)
            document = json.loads(event.canonical_bytes())
            records.append(
                Record(len(records), event.event_type.value, document["payload"], event.leaf_hash())
            )
    tree = SumTree(leaves(records))
    return tree, tree.root(), Oracle(EVAL_DIR)


@pytest.mark.parametrize("entity", [OBLIGATIONS, OUTLAYS])
def test_every_agency_total_and_agency_year_total_matches_the_oracle(
    tree_and_oracle: tuple[SumTree, bytes, Oracle], entity: str
) -> None:
    tree, root, oracle = tree_and_oracle
    agencies = sorted(
        {
            str(r.fields.get("awarding_agency"))
            for r in oracle.records
            if r.fields.get("awarding_agency")
        }
    )
    assert agencies, "the dataset should name some agencies"
    checked = 0
    for agency in agencies:
        expected = oracle.expected({"kind": "sum", "entity": entity, "awarding_agency": agency})
        proven = verify_total(tree.prove(prefix(entity, agency)), root)
        assert proven is not None
        assert Decimal(proven.total) / 100 == expected.amount, agency
        assert proven.count == expected.count, agency
        for year in (2024, 2025):
            want = oracle.expected(
                {"kind": "sum", "entity": entity, "awarding_agency": agency, "fiscal_year": year}
            )
            got = verify_total(tree.prove(prefix(entity, agency, year)), root)
            assert got is not None
            assert (Decimal(got.total) / 100, got.count) == (want.amount, want.count), (
                agency,
                year,
            )
            checked += 1
    assert checked >= 2 * len(agencies)


def test_the_entity_total_matches_the_oracle(
    tree_and_oracle: tuple[SumTree, bytes, Oracle],
) -> None:
    tree, root, oracle = tree_and_oracle
    for entity in (OBLIGATIONS, OUTLAYS):
        expected = oracle.expected({"kind": "sum", "entity": entity})
        proven = verify_total(tree.prove(prefix(entity)), root)
        assert proven is not None
        assert (Decimal(proven.total) / 100, proven.count) == (expected.amount, expected.count)
