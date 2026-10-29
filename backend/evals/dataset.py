"""Build the committed evaluation dataset: whole real awards plus labeled anomalies.

Evaluations need data that is small enough to commit, runs the same in CI as on
a laptop, and still covers every question category. The 2,000-event sample used
by the demo can't do that: it is one day of mostly modifications, with no outlays.

This module picks whole awards from gold (every obligation, modification, and
outlay for the award, so totals are complete), stratified by awarding agency,
and then mixes in anomalies with a fixed seed. Injected events already in gold
are left out first, because their labels were drawn against the full stream.
The selection is deterministic: awards are ranked by a hash of their key.

Usage::

    python -m evals.dataset
"""

import gzip
import hashlib
import json
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from tallyproof_core.events import EventEnvelope
from tallyproof_pipeline.gold import write_events
from tallyproof_pipeline.overlay import Label, inject, write_labels
from tallyproof_pipeline.settings import REPO_ROOT, get_settings

OUT_DIR = REPO_ROOT / "testdata" / "eval"
DEMO_DIR = REPO_ROOT / "var" / "eval-data" / "demo"
DEMO_EVENTS = 20_000
"""The demo streams the first 20,000 gold events (``DATA_SCENARIO=demo``); so does this."""
SEED = 2026
PER_ANOMALY = 3

AGENCIES = 12
"""Agencies with the most awards that have outlays; each contributes awards."""
WITH_OUTLAYS_PER_AGENCY = 20
WITHOUT_OUTLAYS_PER_AGENCY = 5
WITHOUT_OUTLAYS_AGENCIES = 6
WITH_DEOBLIGATIONS = 25
MAX_EVENTS_PER_AWARD = 30
"""Long-running awards with hundreds of modifications would crowd out the rest."""


@dataclass
class AwardStats:
    """What one pass over gold learns about an award."""

    agency: str | None = None
    obligations: int = 0
    outlays: int = 0
    deobligations: int = 0

    @property
    def events(self) -> int:
        """Obligation and outlay events together."""
        return self.obligations + self.outlays


@dataclass(frozen=True)
class Selection:
    """The awards chosen, and why each was chosen."""

    awards: dict[str, str] = field(default_factory=dict)
    """award_key -> reason"""


def _rank(award_key: str) -> str:
    return hashlib.sha256(award_key.encode()).hexdigest()


def _of(agency: str, *, paid: bool) -> Callable[[AwardStats], bool]:
    return lambda s: s.agency == agency and bool(s.outlays) == paid


def select_awards(stats: dict[str, AwardStats]) -> Selection:
    """Choose awards: per agency with and without outlays, plus some with de-obligations.

    Only awards whose original recording is present qualify, so every total the
    evaluation asks about is complete.
    """
    eligible = {
        key: s
        for key, s in stats.items()
        if s.agency is not None and s.events <= MAX_EVENTS_PER_AWARD
    }
    ranked = sorted(eligible, key=_rank)
    with_outlays = Counter(s.agency for s in eligible.values() if s.agency and s.outlays)
    agencies = [agency for agency, _ in with_outlays.most_common(AGENCIES)]
    chosen: dict[str, str] = {}

    def take(reason: str, limit: int, keep: Callable[[AwardStats], object]) -> None:
        taken = 0
        for key in ranked:
            if taken == limit:
                return
            if key not in chosen and keep(eligible[key]):
                chosen[key] = reason
                taken += 1

    for agency in agencies:
        take(f"outlays:{agency}", WITH_OUTLAYS_PER_AGENCY, _of(agency, paid=True))
    for agency in agencies[:WITHOUT_OUTLAYS_AGENCIES]:
        take(f"no-outlays:{agency}", WITHOUT_OUTLAYS_PER_AGENCY, _of(agency, paid=False))
    take("deobligation", WITH_DEOBLIGATIONS, lambda s: s.deobligations and s.outlays)
    return Selection(chosen)


def _lines(path: Path) -> Iterator[dict[str, object]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def scan(gold_events: Path, injected: set[str]) -> dict[str, AwardStats]:
    """One pass over gold, skipping injected events, collecting per-award counts."""
    stats: dict[str, AwardStats] = {}
    for raw in _lines(gold_events):
        if raw["event_id"] in injected:
            continue
        payload: dict[str, str] = raw["payload"]  # type: ignore[assignment]
        s = stats.setdefault(payload["award_key"], AwardStats())
        event_type = raw["event_type"]
        if event_type == "obligation.recorded":
            s.agency = payload["awarding_agency"]
        if str(event_type).startswith("obligation."):
            s.obligations += 1
            if Decimal(payload["amount"]) < 0:
                s.deobligations += 1
        elif event_type == "outlay.reported":
            s.outlays += 1
    return stats


def extract(gold_events: Path, injected: set[str], awards: set[str]) -> list[EventEnvelope]:
    """Second pass: every real event of the chosen awards."""
    return [
        EventEnvelope.model_validate(raw)
        for raw in _lines(gold_events)
        if raw["event_id"] not in injected and raw["payload"]["award_key"] in awards  # type: ignore[index]
    ]


def injected_ids(labels_path: Path) -> set[str]:
    """Event IDs that gold's own overlay injected."""
    with labels_path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    return {row["event_id"] for row in rows if row["event_id"]}


def build(gold_dir: Path, out_dir: Path = OUT_DIR) -> dict[str, object]:
    """Build the dataset from gold and write events, labels, and a manifest."""
    injected = injected_ids(gold_dir / "labels.jsonl")
    selection = select_awards(scan(gold_dir / "events.jsonl.gz", injected))
    real = extract(gold_dir / "events.jsonl.gz", injected, set(selection.awards))
    result = inject(real, seed=SEED, per_anomaly=PER_ANOMALY)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_events(result.events, out_dir / "events.jsonl.gz")
    write_labels(result.labels, out_dir / "labels.jsonl")
    manifest = {
        "seed": SEED,
        "per_anomaly": PER_ANOMALY,
        "awards": len(selection.awards),
        "real_events": len(real),
        "events": len(result.events),
        "labels": dict(sorted(Counter(label.anomaly for label in result.labels).items())),
        "selection": dict(
            sorted(Counter(r.split(":")[0] for r in selection.awards.values()).items())
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_demo(
    gold_dir: Path, out_dir: Path = DEMO_DIR, events: int = DEMO_EVENTS
) -> dict[str, object]:
    """The demo's own slice: the first gold events, with gold's labels that fall inside it.

    Not committed: it is about 2 MB and derived from a local gold build. It exists to
    measure the analyst at the scale the demo runs, where totals pass the citation cap.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    kept: set[str] = set()
    with (
        gzip.open(gold_dir / "events.jsonl.gz", "rt", encoding="utf-8") as source,
        gzip.open(out_dir / "events.jsonl.gz", "wt", encoding="utf-8") as target,
    ):
        for n, line in enumerate(source):
            if n == events:
                break
            kept.add(json.loads(line)["event_id"])
            target.write(line)
    with (gold_dir / "labels.jsonl").open(encoding="utf-8") as handle:
        labels = [json.loads(line) for line in handle]
    inside = [x for x in labels if x["event_id"] in kept]
    with (out_dir / "labels.jsonl").open("w", encoding="utf-8") as handle:
        for label in inside:
            handle.write(json.dumps(label, sort_keys=True) + "\n")
    manifest = {
        "source": "first gold events, as the demo streams them",
        "events": len(kept),
        "labels": dict(sorted(Counter(x["anomaly"] for x in inside).items())),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_labels(out_dir: Path = OUT_DIR) -> list[Label]:
    """Read the dataset's ground truth. Only the evaluation harness may call this."""
    with (out_dir / "labels.jsonl").open(encoding="utf-8") as handle:
        return [Label(**json.loads(line)) for line in handle]


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Rebuild ``testdata/eval``, or the demo-scale slice with ``--scale demo``."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scale", choices=["eval", "demo"], default="eval")
    gold = get_settings().gold_dir
    builder = build_demo if parser.parse_args().scale == "demo" else build
    print(json.dumps(builder(gold), indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
