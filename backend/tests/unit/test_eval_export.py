"""Exporting evaluation reports into the replay bundle."""

import json
from pathlib import Path
from typing import Any

import pytest

from evals.export import ContactDataError, export, rebuild_index, run_name
from evals.readme_table import NotAQualityRunError


def _report(
    run_at: str, label: str = "quality run", answer: str = "Total is $1 [[c1]]."
) -> dict[str, Any]:
    return {
        "run_at": run_at,
        "commit": "abc1234",
        "mode": "live",
        "label": label,
        "cache_misses": 0,
        "models": {"router": "r", "answer": "a"},
        "metrics": {"questions": 1, "numeric_exactness": 1.0, "integrity": 1.0, "tokens": 10},
        "by_set": {"smoke": {"questions": 1, "numeric_exactness": 1.0}},
        "template_vs_held_out_numeric_gap": None,
        "gate_failures": [],
        "results": [
            {
                "set": "smoke",
                "id": "S001",
                "question": "Total?",
                "answer": answer,
                "refusal": None,
                "notes": [],
            }
        ],
    }


def _write(tmp_path: Path, name: str, report: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(report))
    return path


def test_run_name_is_the_utc_stamp():
    assert run_name(_report("2026-10-29T16:46:49+00:00")) == "20261029T164649Z"


def test_export_copies_reports_and_indexes_them_oldest_first(tmp_path):
    out = tmp_path / "evals"
    later = _write(tmp_path, "b.json", _report("2026-10-29T16:46:49+00:00"))
    earlier = _write(tmp_path, "a.json", _report("2026-10-29T01:06:01+00:00"))
    written = export([later, earlier], out)
    assert [p.name for p in written] == ["20261029T164649Z.json", "20261029T010601Z.json"]
    index = json.loads((out / "index.json").read_text())
    assert [r["file"] for r in index["runs"]] == ["20261029T010601Z.json", "20261029T164649Z.json"]
    entry = index["runs"][0]
    assert entry["sets"] == {"smoke": 1}
    assert entry["metrics"]["numeric_exactness"] == 1.0
    assert entry["metrics"]["citation_recall"] is None
    assert entry["gate_failures"] == []
    assert index["gates"]["integrity"]["integrity"] == 1.0


def test_harness_checks_are_refused(tmp_path):
    report = _write(tmp_path, "r.json", _report("2026-10-29T00:00:00+00:00", label="harness check"))
    with pytest.raises(NotAQualityRunError):
        export([report], tmp_path / "evals")
    assert not (tmp_path / "evals" / "index.json").exists()


def test_contact_details_are_refused(tmp_path):
    report = _write(
        tmp_path,
        "r.json",
        _report("2026-10-29T00:00:00+00:00", answer="Write to a.person@example.com."),
    )
    with pytest.raises(ContactDataError):
        export([report], tmp_path / "evals")


def test_reports_from_before_the_commit_field_still_export(tmp_path):
    report = _report("2026-10-29T00:22:11+00:00")
    del report["commit"]
    export([_write(tmp_path, "r.json", report)], tmp_path / "evals")
    index = json.loads((tmp_path / "evals" / "index.json").read_text())
    assert index["runs"][0]["commit"] == "unknown"


def test_index_rebuilds_from_the_folder(tmp_path):
    out = tmp_path / "evals"
    export([_write(tmp_path, "a.json", _report("2026-10-29T01:06:01+00:00"))], out)
    (out / "20261029T010601Z.json").unlink()
    export([_write(tmp_path, "b.json", _report("2026-10-29T16:46:49+00:00"))], out)
    index = rebuild_index(out)
    assert [r["file"] for r in index["runs"]] == ["20261029T164649Z.json"]


def test_baseline_runs_export_with_their_system(tmp_path):
    report = _report("2026-10-29T00:00:00+00:00", label="baseline run")
    report["system"] = "naive"
    export([_write(tmp_path, "r.json", report)], tmp_path / "evals")
    index = json.loads((tmp_path / "evals" / "index.json").read_text())
    assert index["runs"][0]["system"] == "naive"
    assert index["runs"][0]["label"] == "baseline run"
