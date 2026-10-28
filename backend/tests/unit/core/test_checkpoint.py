import base64
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import given
from hypothesis import strategies as st

from tallyproof_core.checkpoint import (
    Checkpoint,
    CheckpointError,
    Signer,
    Verifier,
    decode_private_key,
    encode_private_key,
)

ORIGIN = "tallyproof.dev/log/v1"
ROOT = hashlib.sha256(b"root").digest()

# The worked example from https://c2sp.org/signed-note, "Verifier keys" section.
SPEC_VKEY = "example.com/foo+530d903a+AekyeRrm56hApGFkyQR4ZCbV54Id2LKaANYcrnKv3U2k"
SPEC_NOTE = (
    "This is an example message.\n"
    "\n"
    "— example.com/foo Uw2QOkn8srV1yJGh2VYRlL1Tnagv1YEq6TfXppzi2ONncAlTgK7Ztg1ERYNZXsYjOBH3"
    "mFXmRKuwHjG1Yu72IneyaQM=\n"
)


def make_signer(name: str = ORIGIN, seed: bytes = b"test key") -> Signer:
    return Signer(name, Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed).digest()))


def test_verifies_the_c2sp_specification_example():
    verifier = Verifier.from_verifier_key(SPEC_VKEY)
    assert verifier.verify_note(SPEC_NOTE) == "This is an example message.\n"


def test_signature_lines_start_with_an_em_dash_and_space():
    note = make_signer().sign_note("hello\n")
    signature_line = note.split("\n\n")[1]
    assert signature_line.encode("utf-8").startswith(b"\xe2\x80\x94 ")


def test_checkpoint_round_trip():
    signer = make_signer()
    checkpoint = Checkpoint(ORIGIN, 4211, ROOT)
    note = signer.sign_checkpoint(checkpoint)
    assert Verifier.from_verifier_key(signer.verifier_key()).verify_checkpoint(note) == checkpoint


def test_checkpoint_note_text_layout():
    text = Checkpoint(ORIGIN, 0, ROOT).note_text()
    assert text == f"{ORIGIN}\n0\n{base64.b64encode(ROOT).decode()}\n"


@given(st.integers(0, 200), st.integers(0, 255))
def test_any_change_to_the_signed_text_fails(position, replacement):
    signer = make_signer()
    note = signer.sign_checkpoint(Checkpoint(ORIGIN, 4211, ROOT))
    text_length = len(Checkpoint(ORIGIN, 4211, ROOT).note_text())
    index = position % (text_length - 1)
    new_char = chr(32 + replacement % 95)
    if note[index] == new_char or note[index] == "\n":
        return
    tampered = note[:index] + new_char + note[index + 1 :]
    with pytest.raises(CheckpointError):
        Verifier.from_verifier_key(signer.verifier_key()).verify_checkpoint(tampered)


def test_a_different_key_with_the_same_name_is_rejected():
    note = make_signer(seed=b"attacker").sign_checkpoint(Checkpoint(ORIGIN, 1, ROOT))
    with pytest.raises(CheckpointError, match="not signed by the trusted key"):
        Verifier.from_verifier_key(make_signer().verifier_key()).verify_note(note)


def test_signatures_from_other_keys_are_ignored():
    log = make_signer()
    witness = make_signer(name="witness.example/w1", seed=b"witness")
    note = log.sign_checkpoint(Checkpoint(ORIGIN, 7, ROOT))
    witness_line = witness.sign_note(Checkpoint(ORIGIN, 7, ROOT).note_text()).split("\n\n")[1]
    cosigned = note + witness_line
    verifier = Verifier.from_verifier_key(log.verifier_key())
    assert verifier.verify_checkpoint(cosigned).tree_size == 7


def test_a_failing_signature_from_the_trusted_key_rejects_the_note():
    signer = make_signer()
    note = signer.sign_note("hello\n")
    head, line = note.split("\n\n")
    name, encoded = line.removeprefix("— ").rstrip("\n").split(" ")
    blob = bytearray(base64.b64decode(encoded))
    blob[-1] ^= 1
    broken = f"{head}\n\n— {name} {base64.b64encode(bytes(blob)).decode()}\n"
    with pytest.raises(CheckpointError, match="does not verify"):
        Verifier.from_verifier_key(signer.verifier_key()).verify_note(broken)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (f"{ORIGIN}\n007\n{base64.b64encode(ROOT).decode()}\n", "leading zeros"),
        (f"{ORIGIN}\n7\n{base64.b64encode(b'short').decode()}\n", "32 bytes"),
        (f"{ORIGIN}\n7\n{base64.b64encode(ROOT).decode()}\nextension\n", "exactly"),
        (f"{ORIGIN}\n-1\n{base64.b64encode(ROOT).decode()}\n", "decimal"),
        (f"\n7\n{base64.b64encode(ROOT).decode()}\n", "origin"),
    ],
)
def test_malformed_checkpoint_text_is_rejected(text, message):
    with pytest.raises(CheckpointError, match=message):
        Checkpoint.from_note_text(text)


@pytest.mark.parametrize(
    ("note", "message"),
    [
        ("no signatures here\n", "no signature block"),
        ("text\n\nnot a signature line\n", "malformed signature line"),
        ("text\n\n— example.com/foo AAAA\n", "too short"),
        ("text\n\n— example.com/foo Uw2Q!!\n", "base64"),
        ("bell \x07\n\n— example.com/foo AAAA\n", "control characters"),
    ],
)
def test_malformed_notes_are_rejected(note, message):
    with pytest.raises(CheckpointError, match=message):
        Verifier.from_verifier_key(SPEC_VKEY).verify_note(note)


def test_non_canonical_base64_is_rejected():
    # "Uw==" and "Ux==" decode to the same byte; only the canonical form is allowed.
    with pytest.raises(CheckpointError, match="non-canonical"):
        Verifier.from_verifier_key("example.com/foo+530d903a+Ux==")


@pytest.mark.parametrize(
    ("vkey", "message"),
    [
        ("example.com/foo+530d903a", "three parts"),
        ("example.com/foo+00000000+AekyeRrm56hApGFkyQR4ZCbV54Id2LKaANYcrnKv3U2k", "does not match"),
        ("example.com/foo+530d903a+AgAA", "not an Ed25519"),
        ("bad name+530d903a+AekyeRrm56hApGFkyQR4ZCbV54Id2LKaANYcrnKv3U2k", "invalid key name"),
    ],
)
def test_malformed_verifier_keys_are_rejected(vkey, message):
    with pytest.raises(CheckpointError, match=message):
        Verifier.from_verifier_key(vkey)


def test_private_key_file_format_round_trips():
    key = Ed25519PrivateKey.generate()
    text = encode_private_key(key)
    assert text.startswith("tallyproof-ed25519-private-v1:")
    signer = Signer(ORIGIN, decode_private_key(text + "\n"))
    assert signer.public_key == Signer(ORIGIN, key).public_key


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("ed25519:AAAA", "not a Tallyproof"),
        ("tallyproof-ed25519-private-v1:AAAA", "32 bytes"),
    ],
)
def test_malformed_private_keys_are_rejected(text, message):
    with pytest.raises(CheckpointError, match=message):
        decode_private_key(text)


def test_signing_requires_newline_terminated_text():
    with pytest.raises(CheckpointError, match="newline"):
        make_signer().sign_note("no newline")


def test_invalid_checkpoint_fields_are_rejected():
    with pytest.raises(CheckpointError, match="negative"):
        Checkpoint(ORIGIN, -1, ROOT)
    with pytest.raises(CheckpointError, match="origin"):
        Checkpoint("two\nlines", 1, ROOT)


def test_oversized_notes_and_too_many_signatures_are_rejected():
    verifier = Verifier.from_verifier_key(SPEC_VKEY)
    with pytest.raises(CheckpointError, match="too large"):
        verifier.verify_note("x" * 1_000_001 + "\n\n— a AAAA\n")
    many = "text\n\n" + "— example.com/foo AAAAAAA=\n" * 101
    with pytest.raises(CheckpointError, match="too many"):
        verifier.verify_note(many)


def test_public_key_must_be_32_bytes():
    with pytest.raises(CheckpointError, match="32 bytes"):
        Verifier(ORIGIN, b"\x00" * 31)
