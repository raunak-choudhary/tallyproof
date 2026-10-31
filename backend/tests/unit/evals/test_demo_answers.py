"""The static site's demo answers cite only what the bundle holds, where it holds it."""

import json
from pathlib import Path

import pytest

from evals.demo_answers import (
    BUNDLE,
    BundleMismatchError,
    bundle_records,
    check_citations,
    envelope,
)


def answer(size: int, *cited: tuple[str, int]) -> dict[str, object]:
    return {
        "question": "q",
        "checkpoint_tree_size": size,
        "citations": [{"events": [{"event_id": e, "leaf_index": i} for e, i in cited]}],
        "quotes": [],
    }


RECORDS = [{"event_id": "evt_a", "leaf_index": 0}, {"event_id": "evt_b", "leaf_index": 1}]


def test_the_committed_bundle_is_numbered_in_leaf_order():
    records = bundle_records()
    assert len(records) == json.loads((BUNDLE / "manifest.json").read_text())["tree_size"]


def test_a_bundle_out_of_order_is_refused(tmp_path: Path) -> None:
    (tmp_path / "events.jsonl").write_text(
        '{"event_id": "evt_a", "leaf_index": 1}\n{"event_id": "evt_b", "leaf_index": 0}\n'
    )
    with pytest.raises(BundleMismatchError, match="record 0 sits at leaf 1"):
        bundle_records(tmp_path)


def test_citations_in_the_bundle_pass():
    check_citations([answer(2, ("evt_a", 0), ("evt_b", 1))], RECORDS)


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (answer(3, ("evt_a", 0)), "pinned to 3"),
        (answer(2, ("evt_a", 1)), "evt_a at leaf 1"),
        (answer(2, ("evt_z", 0)), "evt_z"),
    ],
)
def test_a_citation_the_bundle_cant_verify_is_refused(bad, message):
    with pytest.raises(BundleMismatchError, match=message):
        check_citations([bad], RECORDS)


def test_a_bundle_record_becomes_an_event_with_the_same_leaf():
    record = bundle_records()[0]
    assert envelope(record).leaf_document() == json.loads(record["canonical"])
