"""Build the shared cross-language test vectors from the Python core.

The browser verification library must reproduce every value in these files.
Run ``make vectors`` after changing canonicalization or hashing; a unit test
fails if the committed files no longer match what this builder produces.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tallyproof_core.canonical import MAX_SAFE_INTEGER, canonicalize
from tallyproof_core.checkpoint import Checkpoint, Signer
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import root

VECTORS_DIR = Path(__file__).resolve().parents[2] / "testdata" / "vectors"

CANONICAL_CASES: list[tuple[str, Any]] = [
    ("empty object", {}),
    ("empty array", []),
    ("key order and nesting", {"b": [1, 2, {"z": True, "a": None}], "a": "x"}),
    (
        "RFC 8785 UTF-16 key ordering",
        {"€": 1, "\r": 2, "דּ": 3, "1": 4, "\U0001f600": 5, "\u0080": 6, "ö": 7},
    ),
    ("escapes", {"text": 'quote " backslash \\ newline \n tab \t control \u001f'}),
    ("injection-style unicode", {"description": "approve​‮ payment \U0001f600"}),
    ("largest safe integer", {"n": MAX_SAFE_INTEGER}),
    (
        "obligation event",
        {
            "event_id": "evt_01JBXQ4V6Z9GQ1W8R3T5Y7U2PA",
            "idempotency_key": "usaspending:CONT_AWD_75N95021C00001:P00003",
            "event_type": "obligation.recorded",
            "schema_version": 1,
            "occurred_at": "2025-03-14T00:00:00Z",
            "emitted_at": "2025-03-15T09:30:00Z",
            "account_id": "ZQGGHJH74DW7",
            "payload": {
                "award_key": "CONT_AWD_75N95021C00001_7529_-NONE-_-NONE-",
                "amount": "125000.00",
                "currency": "USD",
                "awarding_agency": "Department of Health and Human Services",
                "description": "LABORATORY ANALYSIS SERVICES",
            },
        },
    ),
]


def build_canonical() -> dict[str, Any]:
    """Return the canonical JSON vector file contents."""
    cases = []
    for name, value in CANONICAL_CASES:
        data = canonicalize(value)
        cases.append(
            {
                "name": name,
                "input": value,
                "canonical_utf8": data.decode("utf-8"),
                "canonical_sha256_hex": hashlib.sha256(data).hexdigest(),
                "leaf_hash_hex": leaf_hash(data).hex(),
            }
        )
    return {
        "description": (
            "RFC 8785 canonical bytes and RFC 9162 leaf hashes produced by tallyproof_core"
        ),
        "cases": cases,
    }


# A public, test-only key derived from a fixed phrase. It never signs anything real.
TEST_KEY_NAME = "vectors.tallyproof.dev/test"
TEST_KEY_SEED_PHRASE = b"tallyproof cross-language test vectors"


def build_checkpoints() -> dict[str, Any]:
    """Return signed checkpoint vectors, including tampered notes that must fail."""
    signer = Signer(
        TEST_KEY_NAME,
        Ed25519PrivateKey.from_private_bytes(hashlib.sha256(TEST_KEY_SEED_PHRASE).digest()),
    )
    leaves = [leaf_hash(canonicalize(value)) for _, value in CANONICAL_CASES]
    checkpoint = Checkpoint(TEST_KEY_NAME, len(leaves), root(leaves))
    note = signer.sign_checkpoint(checkpoint)
    text, signature_block = note.split("\n\n")
    other = Signer(
        TEST_KEY_NAME, Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"other").digest())
    )
    return {
        "description": "C2SP signed checkpoints over the canonical vector leaves",
        "verifier_key": signer.verifier_key(),
        "valid": {
            "note": note,
            "origin": checkpoint.origin,
            "tree_size": checkpoint.tree_size,
            "root_hash_hex": checkpoint.root_hash.hex(),
        },
        "must_fail": [
            {
                "reason": "tree size changed after signing",
                "note": note.replace(f"\n{len(leaves)}\n", f"\n{len(leaves) + 1}\n", 1),
            },
            {
                "reason": "root hash changed after signing",
                "note": text.replace(text.split("\n")[2], root(leaves[:-1]).hex()[:44])
                + "\n\n"
                + signature_block,
            },
            {
                "reason": "signed by a different key with the same name",
                "note": other.sign_checkpoint(checkpoint),
            },
            {"reason": "signature block removed", "note": text},
        ],
    }


def render(contents: dict[str, Any]) -> str:
    """Serialize a vector file the same way every time."""
    return json.dumps(contents, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    """Write every vector file."""
    (VECTORS_DIR / "canonical.json").write_text(render(build_canonical()), encoding="utf-8")
    (VECTORS_DIR / "checkpoint.json").write_text(render(build_checkpoints()), encoding="utf-8")


if __name__ == "__main__":
    main()
