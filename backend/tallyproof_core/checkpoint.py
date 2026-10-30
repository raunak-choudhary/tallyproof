"""Signed checkpoints in the C2SP signed-note and tlog-checkpoint formats.

A checkpoint commits to the log's origin, its size, and its Merkle root. It is
signed as a C2SP signed note with Ed25519, the format transparency logs such as
Go's checksum database and Sigstore use, so standard tools can verify it.

Format references:

- https://c2sp.org/signed-note
- https://c2sp.org/tlog-checkpoint

Signature lines must begin with an em dash (U+2014) followed by a space. The
project's no-em-dash writing rule has an explicit exception for this file and
the browser verifier, because the format requires that exact character, and a
test checks it.
"""

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tallyproof_core.hashing import HASH_SIZE

SIGNATURE_TYPE_ED25519 = 0x01
SIGNATURE_LINE_PREFIX = "— "
PRIVATE_KEY_PREFIX = "tallyproof-ed25519-private-v1:"
MAX_NOTE_BYTES = 1_000_000
MAX_SIGNATURES = 100  # the spec requires accepting at least 16

_DECIMAL = re.compile(r"^(0|[1-9][0-9]*)$")


class CheckpointError(ValueError):
    """Raised when a note, checkpoint, or key is malformed or fails verification."""


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(text: str) -> bytes:
    """Decode standard base64, rejecting non-canonical encodings as the spec requires."""
    try:
        data = base64.b64decode(text, validate=True)
    except binascii.Error as error:
        raise CheckpointError("invalid base64") from error
    if _b64encode(data) != text:
        raise CheckpointError("non-canonical base64")
    return data


def _check_key_name(name: str) -> None:
    if not name or any(c.isspace() or c == "+" for c in name):
        raise CheckpointError(f"invalid key name {name!r}")


def key_id(name: str, public_key: bytes) -> bytes:
    """Compute the 4-byte key ID: SHA-256(name || 0x0A || 0x01 || public key)[:4]."""
    data = name.encode("utf-8") + b"\n" + bytes([SIGNATURE_TYPE_ED25519]) + public_key
    return hashlib.sha256(data).digest()[:4]


def encode_private_key(private_key: Ed25519PrivateKey) -> str:
    """Encode a private key in the project's key file format.

    The prefix makes the format easy for secret scanners to recognize, and the
    repository's gitleaks rules block it from ever being committed.
    """
    seed = private_key.private_bytes_raw()
    return PRIVATE_KEY_PREFIX + _b64encode(seed)


def decode_private_key(text: str) -> Ed25519PrivateKey:
    """Read a private key written by :func:`encode_private_key`."""
    text = text.strip()
    if not text.startswith(PRIVATE_KEY_PREFIX):
        raise CheckpointError("not a Tallyproof Ed25519 private key")
    seed = _b64decode(text.removeprefix(PRIVATE_KEY_PREFIX))
    if len(seed) != 32:
        raise CheckpointError("Ed25519 private keys are 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(seed)


@dataclass(frozen=True)
class Checkpoint:
    """A commitment to the log at one size.

    Attributes:
        origin: Identifies the log, for example ``tallyproof.dev/log/v1``.
        tree_size: Number of leaves in the log.
        root_hash: The 32-byte Merkle root at that size.
    """

    origin: str
    tree_size: int
    root_hash: bytes

    def __post_init__(self) -> None:
        """Validate the fields so an invalid checkpoint can never be signed."""
        if not self.origin or "\n" in self.origin:
            raise CheckpointError("origin must be one non-empty line")
        if self.tree_size < 0:
            raise CheckpointError("tree size cannot be negative")
        if len(self.root_hash) != HASH_SIZE:
            raise CheckpointError(f"root hash must be {HASH_SIZE} bytes")

    def note_text(self) -> str:
        """Return the checkpoint as note text: origin, size, and base64 root, each on a line."""
        return f"{self.origin}\n{self.tree_size}\n{_b64encode(self.root_hash)}\n"

    @classmethod
    def from_note_text(cls, text: str) -> "Checkpoint":
        """Parse verified note text back into a checkpoint.

        Extension lines are rejected: the spec does not recommend them, and the
        project never writes them.
        """
        lines = text.split("\n")
        if len(lines) != 4 or lines[3] != "":
            raise CheckpointError("checkpoint must have exactly origin, size, and root lines")
        origin, size, root = lines[:3]
        if not _DECIMAL.match(size):
            raise CheckpointError("tree size must be a decimal without leading zeros")
        return cls(origin, int(size), _b64decode(root))


TOTALS_NOTE_MARKER = "tallyproof-totals/v1"
"""First line of a totals note, so it can never be read as a checkpoint, and back."""


@dataclass(frozen=True)
class TotalsNote:
    """A commitment to the Merkle-sum tree of the log at one size (ADR-0024).

    Attributes:
        origin: The log it was built from, as in that log's checkpoints.
        tree_size: The checkpoint size the tree covers.
        root_hash: The sum tree's 32-byte root.
    """

    origin: str
    tree_size: int
    root_hash: bytes

    def __post_init__(self) -> None:
        """Validate the fields so an invalid note can never be signed."""
        Checkpoint(self.origin, self.tree_size, self.root_hash)  # the same rules apply

    def note_text(self) -> str:
        """Marker, origin, size, and base64 root, each on a line."""
        return (
            f"{TOTALS_NOTE_MARKER}\n{self.origin}\n{self.tree_size}\n{_b64encode(self.root_hash)}\n"
        )

    @classmethod
    def from_note_text(cls, text: str) -> "TotalsNote":
        """Parse verified note text back into a totals note."""
        lines = text.split("\n")
        if len(lines) != 5 or lines[4] != "" or lines[0] != TOTALS_NOTE_MARKER:
            raise CheckpointError("a totals note has a marker, origin, size, and root line")
        origin, size, root = lines[1:4]
        if not _DECIMAL.match(size):
            raise CheckpointError("tree size must be a decimal without leading zeros")
        return cls(origin, int(size), _b64decode(root))


class Signer:
    """Signs notes with one Ed25519 key under one key name."""

    def __init__(self, name: str, private_key: Ed25519PrivateKey) -> None:
        """Create a signer.

        Args:
            name: Key name, normally the log origin.
            private_key: The Ed25519 signing key.
        """
        _check_key_name(name)
        self.name = name
        self._private_key = private_key
        self.public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.key_id = key_id(name, self.public_key)

    def verifier_key(self) -> str:
        """Return the public verifier key string, ``name+hex(key ID)+base64(0x01 || key)``."""
        material = bytes([SIGNATURE_TYPE_ED25519]) + self.public_key
        return f"{self.name}+{self.key_id.hex()}+{_b64encode(material)}"

    def sign_note(self, text: str) -> str:
        """Sign note text and return the complete signed note."""
        if not text.endswith("\n"):
            raise CheckpointError("note text must end with a newline")
        _check_note_characters(text)
        signature = self._private_key.sign(text.encode("utf-8"))
        line = f"{SIGNATURE_LINE_PREFIX}{self.name} {_b64encode(self.key_id + signature)}\n"
        return f"{text}\n{line}"

    def sign_checkpoint(self, checkpoint: Checkpoint) -> str:
        """Sign a checkpoint and return the signed note."""
        return self.sign_note(checkpoint.note_text())

    def sign_totals(self, totals: "TotalsNote") -> str:
        """Sign a totals note and return the signed note."""
        return self.sign_note(totals.note_text())


class Verifier:
    """Verifies notes signed by one known Ed25519 key."""

    def __init__(self, name: str, public_key: bytes) -> None:
        """Create a verifier for a key name and 32-byte public key."""
        _check_key_name(name)
        if len(public_key) != 32:
            raise CheckpointError("Ed25519 public keys are 32 bytes")
        self.name = name
        self.key_id = key_id(name, public_key)
        self._public_key = Ed25519PublicKey.from_public_bytes(public_key)

    @classmethod
    def from_verifier_key(cls, vkey: str) -> "Verifier":
        """Build a verifier from a ``name+hex(key ID)+base64(type || key)`` string."""
        # Only the first two '+' separate fields; the base64 key may contain '+' itself.
        parts = vkey.split("+", 2)
        if len(parts) != 3:
            raise CheckpointError("verifier key must have three parts separated by +")
        name, id_hex, material_b64 = parts
        material = _b64decode(material_b64)
        if len(material) != 33 or material[0] != SIGNATURE_TYPE_ED25519:
            raise CheckpointError("verifier key is not an Ed25519 key")
        verifier = cls(name, material[1:])
        if verifier.key_id.hex() != id_hex:
            raise CheckpointError("verifier key ID does not match the key")
        return verifier

    def verify_note(self, note: str) -> str:
        """Verify a signed note and return its text.

        Signatures from other keys are ignored, as the spec requires. The note is
        rejected if a signature from this key fails, or if none is present.

        Raises:
            CheckpointError: If the note is malformed or not validly signed by this key.
        """
        if len(note.encode("utf-8")) > MAX_NOTE_BYTES:
            raise CheckpointError("note is too large")
        _check_note_characters(note)
        separator = note.rfind("\n\n")
        if separator == -1 or not note.endswith("\n"):
            raise CheckpointError("note has no signature block")
        text = note[: separator + 1]
        signature_lines = note[separator + 2 : -1].split("\n")
        if len(signature_lines) > MAX_SIGNATURES:
            raise CheckpointError("note has too many signatures")

        verified = False
        for line in signature_lines:
            if not line.startswith(SIGNATURE_LINE_PREFIX):
                raise CheckpointError("malformed signature line")
            name, _, encoded = line.removeprefix(SIGNATURE_LINE_PREFIX).partition(" ")
            blob = _b64decode(encoded)
            if len(blob) < 5:
                raise CheckpointError("signature is too short")
            if name != self.name or blob[:4] != self.key_id:
                continue  # someone else's signature, for example a witness cosignature
            try:
                self._public_key.verify(blob[4:], text.encode("utf-8"))
            except InvalidSignature as error:
                raise CheckpointError("signature from the trusted key does not verify") from error
            verified = True
        if not verified:
            raise CheckpointError("note is not signed by the trusted key")
        return text

    def verify_checkpoint(self, note: str) -> Checkpoint:
        """Verify a signed checkpoint note and return the checkpoint it commits to."""
        return Checkpoint.from_note_text(self.verify_note(note))

    def verify_totals(self, note: str) -> TotalsNote:
        """Verify a signed totals note and return what it commits to."""
        return TotalsNote.from_note_text(self.verify_note(note))


def _check_note_characters(text: str) -> None:
    if any(ord(c) < 0x20 and c != "\n" for c in text):
        raise CheckpointError("notes must not contain control characters other than newline")
