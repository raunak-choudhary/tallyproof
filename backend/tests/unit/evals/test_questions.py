import hashlib
from collections import Counter

import pytest

from evals.questions import CATEGORIES, HELD_OUT, load

FROZEN_SHA256 = "8a4144e6bf171293c962977ebe813ca7b6fd0aa68fcdbf52767142e86adee3ab"
"""Changing a held-out question means updating this hash in the same commit, on purpose."""


def test_the_held_out_set_is_frozen():
    assert hashlib.sha256(HELD_OUT.read_bytes()).hexdigest() == FROZEN_SHA256


def test_the_held_out_set_covers_every_category_with_hand_checked_answers():
    questions = load(HELD_OUT)
    assert len(questions) == 40
    assert set(Counter(q.category for q in questions)) == CATEGORIES
    assert sum(q.verified is not None for q in questions) == 10
    assert all(q.must_not_say for q in questions if q.category == "injection")
    assert not any(q.answerable for q in questions if q.category == "refusal")


def test_bad_files_are_rejected(tmp_path):
    path = tmp_path / "q.toml"
    row = '[[question]]\nid = "X"\ntext = "t"\ncategory = "%s"\nexpect = { kind = "sum" }\n'
    path.write_text(row % "lookup" + row % "lookup")
    with pytest.raises(ValueError, match="duplicate"):
        load(path)
    path.write_text(row % "astrology")
    with pytest.raises(ValueError, match="unknown categories"):
        load(path)
