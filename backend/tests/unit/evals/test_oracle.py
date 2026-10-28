import subprocess
import sys
from decimal import Decimal

import pytest

from evals import golden
from evals.oracle import Oracle
from evals.questions import HELD_OUT, load


@pytest.fixture(scope="module")
def oracle() -> Oracle:
    return Oracle()


def test_the_oracle_shares_no_code_with_the_analyst():
    banned = "('apps', 'tallyproof_core.reconciliation', 'django')"
    code = (
        "import sys, evals.oracle, evals.golden; "
        f"print(sorted(m for m in sys.modules if m.startswith({banned})))"
    )
    out = subprocess.run(  # noqa: S603 - fixed arguments, the test's own interpreter
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"


def test_the_oracle_agrees_with_every_hand_checked_answer(oracle):
    checked = [q for q in load(HELD_OUT) if q.verified]
    assert len(checked) == 10
    for q in checked:
        expected = oracle.expected(q.expect)
        v = q.verified
        assert v is not None
        if "amount" in v:
            assert expected.amount == Decimal(v["amount"]), q.id
        if "events" in v:
            assert len(expected.must_cite) == v["events"], q.id
        if "count" in v:
            assert expected.count == v["count"], q.id
        if "group" in v:
            assert expected.group == v["group"], q.id
        if "event_id" in v:
            assert expected.must_cite == {v["event_id"]}, q.id
        if "event_ids" in v:
            assert expected.must_cite == set(v["event_ids"]), q.id
        for name in ("piid", "modification_number", "action_date"):
            if name in v:
                assert expected.fields[name] == v[name], q.id


@pytest.mark.parametrize("path", [HELD_OUT, golden.SMOKE, golden.FULL], ids=lambda p: p.stem)
def test_every_question_has_a_computable_answer(oracle, path):
    for q in load(path):
        expected = oracle.expected(q.expect)
        if not q.answerable:
            assert expected.refuse, q.id
        elif q.category == "policy":
            assert expected.section in oracle.sections, q.id
        elif q.expect["kind"] == "average_per_award":
            assert expected.amount is not None, q.id
        else:
            assert expected.refuse is None, q.id
            assert expected.must_cite or expected.count == 0, q.id
            assert expected.must_cite <= expected.may_cite, q.id


def test_lookups_in_the_template_sets_pick_exactly_one_record(oracle):
    for q in load(golden.FULL):
        if q.expect["kind"] == "lookup":
            assert len(oracle.expected(q.expect).must_cite) == 1, q.id


def test_the_committed_question_sets_match_a_rebuild(oracle, tmp_path):
    smoke, full = tmp_path / "smoke.toml", tmp_path / "full.toml"
    assert golden.write(oracle, smoke, full) == (20, 178)
    assert smoke.read_text() == golden.SMOKE.read_text()
    assert full.read_text() == golden.FULL.read_text()
