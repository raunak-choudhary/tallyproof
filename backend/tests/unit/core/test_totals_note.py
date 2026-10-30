"""Signed totals notes: they verify, and they never pass for a checkpoint (or the reverse)."""

import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tallyproof_core.checkpoint import (
    Checkpoint,
    CheckpointError,
    Signer,
    TotalsNote,
    Verifier,
)

ORIGIN = "tallyproof.test/log/v1"
ROOT = hashlib.sha256(b"sum root").digest()


@pytest.fixture
def signer() -> Signer:
    return Signer("tallyproof-test", Ed25519PrivateKey.generate())


def test_a_signed_totals_note_verifies(signer: Signer) -> None:
    note = signer.sign_totals(TotalsNote(ORIGIN, 1792, ROOT))
    verified = Verifier.from_verifier_key(signer.verifier_key()).verify_totals(note)
    assert verified == TotalsNote(ORIGIN, 1792, ROOT)


def test_another_key_is_refused(signer: Signer) -> None:
    note = signer.sign_totals(TotalsNote(ORIGIN, 10, ROOT))
    other = Signer("tallyproof-test", Ed25519PrivateKey.generate())
    with pytest.raises(CheckpointError):
        Verifier.from_verifier_key(other.verifier_key()).verify_totals(note)


def test_a_totals_note_is_never_a_checkpoint(signer: Signer) -> None:
    verifier = Verifier.from_verifier_key(signer.verifier_key())
    with pytest.raises(CheckpointError):
        verifier.verify_checkpoint(signer.sign_totals(TotalsNote(ORIGIN, 10, ROOT)))


def test_a_checkpoint_is_never_a_totals_note(signer: Signer) -> None:
    verifier = Verifier.from_verifier_key(signer.verifier_key())
    with pytest.raises(CheckpointError):
        verifier.verify_totals(signer.sign_checkpoint(Checkpoint(ORIGIN, 10, ROOT)))


@pytest.mark.parametrize(
    "text",
    [
        f"tallyproof-totals/v2\n{ORIGIN}\n10\n{'A' * 44}\n",
        f"tallyproof-totals/v1\n{ORIGIN}\n010\n{'A' * 43}=\n",
        f"tallyproof-totals/v1\n{ORIGIN}\n10\n",
    ],
)
def test_malformed_totals_text_is_refused(text: str) -> None:
    with pytest.raises(CheckpointError):
        TotalsNote.from_note_text(text)
