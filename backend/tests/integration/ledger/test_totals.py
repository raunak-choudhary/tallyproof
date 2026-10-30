"""Signing the Merkle-sum tree of a checkpoint, on a real database."""

import psycopg
import pytest

from apps.ledger.totals import TotalsSigner, build_tree
from tallyproof_core.checkpoint import Verifier
from tallyproof_core.sum_tree import verify_total
from tallyproof_core.totals import OBLIGATIONS, prefix
from tests.fakes import FrozenClock
from tests.integration.conftest import Database
from tests.integration.ledger.test_checkpointer import add_events
from tests.unit.pipeline.test_replay_bundle import SIGNER

pytestmark = pytest.mark.django_db


def test_signed_totals_prove_the_sum_of_the_checkpoint(migrated: Database) -> None:
    add_events(migrated, 4)  # four obligations of 1,250.00 for the Department of Energy
    signed = TotalsSigner(SIGNER, 50_000, 300, clock=FrozenClock()).sign(4)
    note = Verifier.from_verifier_key(SIGNER.verifier_key()).verify_totals(signed.note)
    assert (note.tree_size, note.root_hash) == (4, signed.root_hash)
    tree = build_tree(4)
    proven = verify_total(tree.prove(prefix(OBLIGATIONS, "Department of Energy")), note.root_hash)
    assert proven is not None
    assert (proven.total, proven.count) == (500_000, 4)


def test_a_checkpoint_covers_only_its_own_records(migrated: Database) -> None:
    add_events(migrated, 5)
    assert build_tree(3).size == 3
    assert build_tree(3).root() != build_tree(5).root()


def test_small_logs_get_totals_at_every_checkpoint(migrated: Database) -> None:
    add_events(migrated, 3)
    signer = TotalsSigner(
        SIGNER, every_checkpoint_up_to=10, interval_seconds=300, clock=FrozenClock()
    )
    assert signer.maybe_sign(2) is not None
    assert signer.maybe_sign(2) is None  # already signed
    assert signer.maybe_sign(3) is not None


def test_large_logs_wait_for_the_interval(migrated: Database) -> None:
    add_events(migrated, 4)
    clock = FrozenClock()
    signer = TotalsSigner(SIGNER, every_checkpoint_up_to=1, interval_seconds=300, clock=clock)
    assert signer.maybe_sign(2) is not None  # the first one is always due
    assert signer.maybe_sign(3) is None
    clock.advance(300)
    assert signer.maybe_sign(4) is not None


def test_a_restarted_signer_continues_from_the_newest_totals(migrated: Database) -> None:
    add_events(migrated, 2)
    TotalsSigner(SIGNER, 50_000, 300, clock=FrozenClock()).sign(2)
    again = TotalsSigner(SIGNER, 50_000, 300, clock=FrozenClock())
    assert again.signed_size == 2
    assert not again.due(2)


def test_signed_totals_cannot_be_changed_or_removed(migrated: Database) -> None:
    with migrated.connect("app") as conn:
        conn.execute(
            "INSERT INTO ledger_totals (tree_size, root_hash, totals_note, records)"
            " VALUES (1, %s, 'note', 1)",
            [bytes(32)],
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE ledger_totals SET records = 0")
    with migrated.connect("owner") as conn:
        for statement in ("UPDATE ledger_totals SET records = 0", "DELETE FROM ledger_totals"):
            with pytest.raises(psycopg.errors.DatabaseError):
                conn.execute(statement)
