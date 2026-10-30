"""Choosing and writing the replay bundle's witnessed checkpoint."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tallyproof_pipeline.replay_witness import choose, write


def _bundle(tmp_path: Path, sizes: list[int]) -> Path:
    lines = [json.dumps({"tree_size": s, "note": f"origin\n{s}\nroot{s}=\n"}) for s in sizes]
    (tmp_path / "checkpoints.jsonl").write_text("\n".join(lines) + "\n")
    return tmp_path


def test_chooses_the_newest_checkpoint_below_the_whole_log(tmp_path):
    assert choose(_bundle(tmp_path, [256, 512, 768, 900]))["tree_size"] == 768


def test_chooses_a_named_size(tmp_path):
    assert choose(_bundle(tmp_path, [256, 512, 900]), 256)["tree_size"] == 256
    with pytest.raises(ValueError, match="no checkpoint at size 300"):
        choose(_bundle(tmp_path, [256, 512, 900]), 300)


def test_refuses_a_bundle_with_nothing_to_extend(tmp_path):
    with pytest.raises(ValueError, match="only one checkpoint"):
        choose(_bundle(tmp_path, [900]))


def test_writes_the_export_line_and_the_note(tmp_path):
    out = tmp_path / "witness"
    note = write(
        {"tree_size": 768, "note": "origin\n768\nroot=\n\n- sig\n"},
        out,
        now=datetime(2026, 10, 30, tzinfo=UTC),
    )
    assert note.name == "checkpoint-768.note"
    assert note.read_text() == "origin\n768\nroot=\n\n- sig\n"
    record = json.loads((out / "checkpoints.jsonl").read_text())
    assert record == {
        "exported_at": "2026-10-30T00:00:00+00:00",
        "tree_size": 768,
        "note": "origin\n768\nroot=\n\n- sig\n",
    }
