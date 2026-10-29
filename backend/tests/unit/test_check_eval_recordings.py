import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "check_eval_recordings", ROOT / "scripts" / "ci" / "check_eval_recordings.py"
)
assert _spec is not None
assert _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

QUALITY = {"label": "quality run", "cache_misses": 0}
HARNESS = {"label": "harness check", "cache_misses": 7}


def test_a_quality_run_always_passes():
    assert guard.verdict(QUALITY, ["backend/apps/analyst/router.py"])[0] == 0


def test_a_harness_check_fails_only_when_the_change_touches_what_is_measured():
    code, message = guard.verdict(HARNESS, ["backend/apps/analyst/pipeline.py", "README.md"])
    assert code == 1
    assert "make eval-record" in message
    assert "backend/apps/analyst/pipeline.py" in message
    assert "README.md" not in message
    for path in (
        "backend/evals/questions/smoke.toml",
        "backend/corpus/far/part-4.jsonl",
        "testdata/eval/labels.jsonl",
    ):
        assert guard.verdict(HARNESS, [path])[0] == 1, path
    assert guard.verdict(HARNESS, ["docs/testing.md", "frontend/src/app/page.tsx"])[0] == 0


def test_a_missing_report_fails():
    assert guard.verdict(None, [])[0] == 1


def test_the_newest_report_is_read(tmp_path):
    for stamp, label in (
        ("20261028T000000Z", "harness check"),
        ("20261029T000000Z", "quality run"),
    ):
        (tmp_path / stamp).mkdir()
        (tmp_path / stamp / "report.json").write_text(json.dumps({"label": label}))
    assert guard.newest_report(tmp_path) == {"label": "quality run"}
    assert guard.newest_report(tmp_path / "missing") is None
