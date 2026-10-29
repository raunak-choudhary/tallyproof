"""Every dataset committed to this public repository is free of contact details."""

import gzip
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from tallyproof_core.contact_data import find_contact_data

ROOT = Path(__file__).resolve().parents[3]
DATASETS = [
    ROOT / "testdata" / "eval" / "events.jsonl.gz",
    ROOT / "testdata" / "sample" / "gold_events_sample.jsonl.gz",
    ROOT / "frontend" / "public" / "replay" / "events.jsonl",
]


def lines(path: Path) -> Iterator[str]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as compressed:
            yield from compressed
    else:
        with path.open(encoding="utf-8") as plain:
            yield from plain


@pytest.mark.parametrize("path", DATASETS, ids=[p.name for p in DATASETS])
def test_committed_events_carry_no_contact_details(path):
    offenders = []
    for n, line in enumerate(lines(path), start=1):
        record = json.loads(line)
        text = record.get("canonical") or json.dumps(record.get("payload", {}))
        if find_contact_data(text):
            offenders.append(n)
    assert offenders == [], f"{path.name}: lines {offenders[:5]} carry contact details"
