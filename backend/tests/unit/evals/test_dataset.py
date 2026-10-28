import json

from evals import dataset
from evals.dataset import AwardStats, load_labels, select_awards
from tallyproof_pipeline.gold import read_events


def stats() -> dict[str, AwardStats]:
    awards = {}
    for i in range(60):
        agency = "Energy" if i % 2 else "Defense"
        awards[f"A{i}"] = AwardStats(agency, obligations=2, outlays=i % 3, deobligations=i % 7 == 0)
    awards["orphan"] = AwardStats(None, obligations=1, outlays=3)
    awards["huge"] = AwardStats("Energy", obligations=dataset.MAX_EVENTS_PER_AWARD, outlays=5)
    return awards


def test_selection_is_stratified_complete_and_deterministic():
    chosen = select_awards(stats()).awards
    assert chosen == select_awards(dict(reversed(stats().items()))).awards
    assert "orphan" not in chosen  # no original recording, so its totals would be incomplete
    assert "huge" not in chosen
    reasons = set(chosen.values())
    assert {
        "outlays:Energy",
        "outlays:Defense",
        "no-outlays:Energy",
        "no-outlays:Defense",
    } <= reasons
    for key, reason in chosen.items():
        assert bool(stats()[key].outlays) == (not reason.startswith("no-outlays"))


def test_the_committed_dataset_matches_its_manifest():
    manifest = json.loads((dataset.OUT_DIR / "manifest.json").read_text())
    events = list(read_events(dataset.OUT_DIR / "events.jsonl.gz"))
    labels = load_labels()
    assert len(events) == manifest["events"]
    assert len(labels) == sum(manifest["labels"].values())
    ids = {e.event_id for e in events}
    assert all(label.event_id in ids for label in labels if label.anomaly != "schema_invalid")
