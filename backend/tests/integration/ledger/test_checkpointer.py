import json

import pytest

from apps.ledger import timestamps
from apps.ledger.checkpointer import Checkpointer, CheckpointerError, WitnessPolicy
from apps.ledger.timestamps import StampResult
from apps.ledger.witness import verify
from tallyproof_core.checkpoint import Verifier
from tallyproof_core.log_tree import LogTree
from tests.integration.conftest import Database
from tests.integration.ledger.test_schema import INSERT, event, row
from tests.unit.pipeline.test_replay_bundle import SIGNER

pytestmark = pytest.mark.django_db


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def add_events(database: Database, count: int, start: int = 0) -> None:
    with database.connect("app") as conn:
        for i in range(start, start + count):
            conn.execute(INSERT, row(event(), i))


def test_a_batch_closes_when_it_is_full(migrated):
    add_events(migrated, 5)
    cp = Checkpointer(SIGNER, batch_max_size=4, batch_max_age_ms=60_000, clock=Clock())
    signed = cp.tick()
    assert signed is not None
    assert (signed.start_index, signed.tree_size) == (0, 5)
    checkpoint = Verifier.from_verifier_key(SIGNER.verifier_key()).verify_checkpoint(signed.note)
    assert checkpoint.root_hash == cp.tree.root(5)
    assert cp.tick() is None


def test_a_batch_closes_when_its_oldest_leaf_is_old_enough(migrated):
    clock = Clock()
    add_events(migrated, 2)
    cp = Checkpointer(SIGNER, batch_max_size=256, batch_max_age_ms=2000, clock=clock)
    assert cp.tick() is None
    assert cp.seconds_until_due() == pytest.approx(2.0)
    clock.now += 2.0
    signed = cp.tick()
    assert signed is not None
    assert signed.tree_size == 2
    assert cp.seconds_until_due() is None


def test_a_restarted_checkpointer_continues_from_the_last_signed_size(migrated):
    add_events(migrated, 3)
    first = Checkpointer(SIGNER, 1, 60_000, clock=Clock())
    first.tick()
    add_events(migrated, 2, start=3)
    second = Checkpointer(SIGNER, 1, 60_000, clock=Clock())
    signed = second.tick()
    assert signed is not None
    assert (signed.start_index, signed.tree_size) == (3, 5)


def test_it_refuses_to_sign_after_a_signed_leaf_is_rewritten(migrated):
    add_events(migrated, 4)
    Checkpointer(SIGNER, 1, 60_000, clock=Clock()).tick()
    forged = event()  # a whole new, internally consistent row in place of leaf 1
    with migrated.connect("superuser") as conn:
        conn.execute("ALTER TABLE ledger_event DISABLE TRIGGER USER")
        conn.execute("DELETE FROM ledger_event WHERE leaf_index = 1")
        conn.execute(INSERT, row(forged, 1))
        conn.execute("ALTER TABLE ledger_event ENABLE TRIGGER USER")
    with pytest.raises(CheckpointerError, match="no longer match"):
        Checkpointer(SIGNER, 1, 60_000, clock=Clock())


def test_a_missing_leaf_is_detected(migrated):
    add_events(migrated, 2)
    add_events(migrated, 1, start=5)
    with pytest.raises(CheckpointerError, match="leaf 2 is missing"):
        Checkpointer(SIGNER, 1, 60_000, clock=Clock())


def test_checkpoints_are_exported_timestamped_and_verifiable(migrated, tmp_path, monkeypatch):
    stamped: list[str] = []

    def fake_stamp(data, target, calendars):
        stamped.append(target.name)
        proof = target.with_name(target.name + ".cal.example.ots")
        proof.write_bytes(b"proof")
        return StampResult([proof], {})

    monkeypatch.setattr(timestamps, "stamp", fake_stamp)
    policy = WitnessPolicy(tmp_path / "checkpoints.jsonl", 3600, ["https://cal.example"])
    clock = Clock()
    cp = Checkpointer(SIGNER, 2, 60_000, witness=policy, clock=clock)
    add_events(migrated, 2)
    cp.tick()
    add_events(migrated, 2, start=2)
    cp.tick()
    lines = [json.loads(line) for line in policy.export_path.read_text().splitlines()]
    assert [line["tree_size"] for line in lines] == [2, 4]
    assert stamped == ["checkpoint-2.note"]  # once per witness interval

    verifier = Verifier.from_verifier_key(SIGNER.verifier_key())
    report = verify(policy.export_path, verifier, cp.tree)
    assert (report.ok, report.checked, report.timestamped) == (True, 2, 1)

    rewritten = LogTree()
    for i in range(4):
        rewritten.append(cp.tree.leaf(i) if i != 0 else bytes(32))
    tampered = verify(policy.export_path, verifier, rewritten)
    assert not tampered.ok
    assert "no longer matches checkpoint 2" in tampered.problems[0]
