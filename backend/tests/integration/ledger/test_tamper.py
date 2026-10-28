import json
from typing import Any

import psycopg
import pytest

from apps.ledger import tamper
from tallyproof_core.canonical import canonicalize
from tallyproof_core.checkpoint import Checkpoint, CheckpointError, Verifier
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.log_tree import LogTree
from tallyproof_core.merkle import verify_inclusion
from tests.integration.ledger.test_schema import INSERT, event, row
from tests.unit.pipeline.test_replay_bundle import SIGNER

VERIFIER = Verifier.from_verifier_key(SIGNER.verifier_key())


@pytest.fixture
def signed(migrated):
    """Four committed events and a signed checkpoint over them."""
    events = [event() for _ in range(4)]
    with migrated.connect("app") as conn:
        for i, e in enumerate(events):
            conn.execute(INSERT, row(e, i))
        tree = LogTree()
        for e in events:
            tree.append(e.leaf_hash())
        note = SIGNER.sign_checkpoint(Checkpoint(SIGNER.name, 4, tree.root()))
        conn.execute(
            "INSERT INTO ledger_batch (public_id, start_index, tree_size, root_hash,"
            " checkpoint_note, key_id) VALUES ('bat_01TEST', 0, 4, %s, %s, 'k')",
            [tree.root(), note],
        )
    yield migrated, events
    with migrated.connect("superuser") as conn:
        conn.execute("ALTER TABLE ledger_batch DISABLE TRIGGER USER")
        conn.execute("DELETE FROM ledger_batch")
        conn.execute("ALTER TABLE ledger_batch ENABLE TRIGGER USER")


def state(conn: psycopg.Connection[Any]) -> tuple[LogTree, str, list[bytes]]:
    rows = conn.execute("SELECT canonical_bytes FROM ledger_event ORDER BY leaf_index").fetchall()
    tree = LogTree()
    for (canonical,) in rows:
        tree.append(leaf_hash(bytes(canonical)))
    batch = conn.execute("SELECT checkpoint_note FROM ledger_batch").fetchone()
    assert batch is not None
    note: str = batch[0]
    return tree, note, [bytes(r[0]) for r in rows]


def test_level_1_breaks_inclusion_against_the_signed_root(signed):
    database, events = signed
    with database.connect("owner") as conn:
        tamper.edit_event(conn, events[1].event_id, "999.00")
        tree, note, rows = state(conn)
    edited = json.loads(rows[1])
    assert rows[1] == canonicalize(edited)  # still canonical: only the hashes give it away
    checkpoint = VERIFIER.verify_checkpoint(note)
    assert not verify_inclusion(tree.leaf(1), 1, 4, tree.inclusion_proof(1), checkpoint.root_hash)


def test_level_2_breaks_the_signature(signed):
    database, events = signed
    with database.connect("owner") as conn:
        tamper.edit_event(conn, events[1].event_id, "999.00")
        tamper.rebuild_checkpoint(conn)
        _, note, _ = state(conn)
    with pytest.raises(CheckpointError):
        VERIFIER.verify_checkpoint(note)


def test_level_3_passes_signatures_but_not_the_witnessed_root(signed):
    database, events = signed
    with database.connect("owner") as conn:
        _, witnessed_note, _ = state(conn)
        tamper.edit_event(conn, events[1].event_id, "999.00")
        tamper.rebuild_checkpoint(conn, SIGNER)
        tree, note, _ = state(conn)
    forged = VERIFIER.verify_checkpoint(note)  # the stolen key signs it fine
    witnessed = VERIFIER.verify_checkpoint(witnessed_note)
    assert forged.root_hash != witnessed.root_hash
    assert tree.root(4) != witnessed.root_hash  # what verify_witness reports


def test_restore_undoes_every_level(signed):
    database, events = signed
    with database.connect("owner") as conn:
        before = state(conn)
        backup = {"event": tamper.edit_event(conn, events[2].event_id, "1.00")}
        backup["checkpoint"] = tamper.rebuild_checkpoint(conn, SIGNER)
        tamper.restore(conn, backup)
        after = state(conn)
    assert after[1:] == before[1:]


def test_the_guards_refuse_unless_enabled_and_local():
    with pytest.raises(tamper.TamperRefusedError, match="DEMO_TAMPER_ENABLED"):
        tamper.check_safe(False, "localhost")
    with pytest.raises(tamper.TamperRefusedError, match="loopback"):
        tamper.check_safe(True, "203.0.113.9")
    tamper.check_safe(True, "127.0.0.1")
