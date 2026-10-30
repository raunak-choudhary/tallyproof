"""Run the reconciliation rules over gold and score them against the overlay's labels.

Streams the gold events in log order through the same engine the projection uses
(:class:`tallyproof_core.reconciliation.Reconciler`), duplicates first refused as the
ledger would refuse them, and reports for each labelled anomaly how many its rule
caught. Breaks no label explains are counted too: on real data some are genuine
findings, and the report says how many so a reader can judge the rule's precision.

Usage::

    python -m tallyproof_pipeline.recon_report       # make recon-report
"""

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from tallyproof_core.reconciliation import Reconciler
from tallyproof_pipeline.gold import read_events
from tallyproof_pipeline.settings import get_settings

RULE_FOR = {
    "deobligation_exceeds_award": "deobligation_exceeds_award",
    "duplicate_award_semantic": "possible_duplicate_award",
    "late_arrival": "late_after_close",
    "orphan_outlay": "orphan_outlay",
    "outlay_exceeds_obligation": "outlay_exceeds_obligation",
    "recipient_burst": "recipient_burst",
}


def score(labels: list[dict[str, Any]], found: dict[str, set[str]]) -> dict[str, dict[str, int]]:
    """Caught and labelled counts per anomaly; a label is caught if its event is in a break."""
    out: dict[str, dict[str, int]] = {}
    for anomaly, rule in RULE_FOR.items():
        wanted = [x["event_id"] for x in labels if x["anomaly"] == anomaly and x["event_id"]]
        out[anomaly] = {
            "labelled": len(wanted),
            "caught": sum(e in found.get(rule, set()) for e in wanted),
        }
    return out


def main() -> None:  # pragma: no cover - exercised by make recon-report
    """Score the rules over the gold build and write data/gold/recon_report.json."""
    gold = get_settings().gold_dir
    labels = [json.loads(line) for line in (gold / "labels.jsonl").open(encoding="utf-8")]
    labelled = {x["event_id"] for x in labels if x["event_id"]}
    for x in labels:
        if x["anomaly"] == "recipient_burst":
            labelled.update(x["related_event_ids"])
    engine = Reconciler()
    seen: set[str] = set()
    found: dict[str, set[str]] = {}
    unexplained: Counter[str] = Counter()
    started = time.monotonic()
    events = 0
    for event in read_events(gold / "events.jsonl.gz"):
        if event.idempotency_key in seen:
            continue
        seen.add(event.idempotency_key)
        events += 1
        for b in engine.apply(event):
            ids = {e for e, _ in b.events}
            found.setdefault(b.break_type.value, set()).update(ids)
            if not ids & labelled:
                unexplained[b.break_type.value] += 1
    report = {
        "events": events,
        "seconds": round(time.monotonic() - started, 1),
        "by_anomaly": score(labels, found),
        "breaks_no_label_explains": dict(sorted(unexplained.items())),
    }
    path = Path(gold) / "recon_report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
