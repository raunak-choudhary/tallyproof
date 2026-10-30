"""Build the shared cross-language test vectors from the Python core.

The browser verification library must reproduce every value in these files.
Run ``make vectors`` after changing canonicalization or hashing; a unit test
fails if the committed files no longer match what this builder produces.
"""

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tallyproof_core.canonical import MAX_SAFE_INTEGER, canonicalize
from tallyproof_core.checkpoint import Checkpoint, Signer, TotalsNote
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import root
from tallyproof_core.sum_tree import (
    LeafPiece,
    NodePiece,
    SumLeaf,
    SumTree,
    TotalProof,
    proof_to_json,
    verify_total,
)

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
    (
        "policy event",
        {
            "event_id": "evt_01KQ3Z1XW0000000000000000A",
            "idempotency_key": "ecfr:far:32.906:4c1f0e2a9b7d3e55",
            "event_type": "policy.published",
            "schema_version": 1,
            "occurred_at": "2026-10-19T00:00:00Z",
            "emitted_at": "2026-10-19T00:00:00Z",
            "account_id": "policy-far",
            "payload": {
                "source": "FAR",
                "citation": "48 CFR 32.906",
                "section": "32.906",
                "title": "Making payments.",
                "edition": "2026-10-19",
                "text": (
                    "(a) General. The Government will not make invoice payments earlier than"
                    " 7 days prior to the due dates specified in the contract unless the"
                    " agency head determines\u2014\n\n(1) To make earlier payment on a"
                    " case-by-case basis; or"
                ),
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


SUM_ROWS: list[tuple[str, str, str, int]] = [
    ("obligations", "Agency A", "2024", 12_500_000),
    ("obligations", "Agency A", "2025", -796_000),
    ("obligations", "Agency A", "2024", 1),
    ("obligations", "Agency AB", "2024", 99),
    ("obligations", "", "2024", 4_200),
    ("obligations", "Département é", "2025", 31_415),
    ("obligations", "Agency B", "", 0),
    ("outlays", "Agency A", "2024", 158_172),
    ("outlays", "Département é", "2024", 7),
    ("outlays", "", "2024", 900),
    ("outlays", "Agency A", "2024", -50),
    ("obligations", "Agency A", "2025", 2_000_000_000_000),
    ("outlays", "Agency AB", "2025", 3),
]
"""(entity, agency, fiscal year, cents); the leaf index is the row's position."""

SUM_PREFIXES: list[tuple[str, ...]] = [
    (),
    ("obligations",),
    ("obligations", "Agency A"),
    ("obligations", "Agency A", "2024"),
    ("obligations", "Agency AB"),
    ("obligations", ""),
    ("outlays", "Département é"),
    ("outlays", "Agency B"),
    ("nothing",),
]


def build_sum_tree() -> dict[str, Any]:
    """A small Merkle-sum tree, honest total proofs, and forged ones that must fail."""
    leaves = [
        SumLeaf((e, a, y, f"{n:020d}"), amount, hashlib.sha256(f"record {n}".encode()).digest())
        for n, (e, a, y, amount) in enumerate(SUM_ROWS)
    ]
    tree = SumTree(leaves, cache_min=1)
    root_hash = tree.root()
    cases = []
    for prefix in SUM_PREFIXES:
        proof = tree.prove(prefix)
        proven = verify_total(proof, root_hash)
        assert proven is not None
        cases.append(
            {
                "prefix": list(prefix),
                "proof": proof_to_json(proof),
                "total": str(proven.total),
                "count": proven.count,
            }
        )

    agency_a = ("obligations", "Agency A")
    honest = tree.prove(agency_a)
    start, end = tree.run(agency_a)
    node = next(i for i, p in enumerate(honest.pieces) if isinstance(p, NodePiece))
    leaf = next(i for i, p in enumerate(honest.pieces) if isinstance(p, LeafPiece))

    def with_piece(index: int, piece: LeafPiece | NodePiece) -> TotalProof:
        pieces = list(honest.pieces)
        pieces[index] = piece
        return dataclasses.replace(honest, pieces=tuple(pieces))

    inflated = honest.pieces[node]
    changed = honest.pieces[leaf]
    assert isinstance(inflated, NodePiece)
    assert isinstance(changed, LeafPiece)
    forged = [
        (
            "a subtree's sum inflated",
            with_piece(node, dataclasses.replace(inflated, total=inflated.total + 100)),
        ),
        (
            "a record's amount changed",
            with_piece(
                leaf, LeafPiece(dataclasses.replace(changed.leaf, amount=changed.leaf.amount + 1))
            ),
        ),
        ("the run made one record shorter, hiding it", tree._prove(agency_a, start + 1, end)),
        ("the run widened past the prefix", tree._prove(agency_a, start, end + 1)),
        ("a piece dropped", dataclasses.replace(honest, pieces=honest.pieces[:-1])),
    ]
    must_fail = []
    for reason, proof in forged:
        assert verify_total(proof, root_hash) is None, reason
        must_fail.append({"reason": reason, "proof": proof_to_json(proof)})
    signer = Signer(
        TEST_KEY_NAME,
        Ed25519PrivateKey.from_private_bytes(hashlib.sha256(TEST_KEY_SEED_PHRASE).digest()),
    )
    return {
        "verifier_key": signer.verifier_key(),
        "totals_note": signer.sign_totals(TotalsNote(TEST_KEY_NAME, len(leaves), root_hash)),
        "checkpoint_note_with_the_same_root": signer.sign_checkpoint(
            Checkpoint(TEST_KEY_NAME, len(leaves), root_hash)
        ),
        "leaves": [
            {
                "key": list(leaf.key),
                "amount": str(leaf.amount),
                "record_hash": leaf.record_hash.hex(),
            }
            for leaf in leaves
        ],
        "root_hex": root_hash.hex(),
        "total": str(tree.total()),
        "cases": cases,
        "must_fail": must_fail,
    }


def render(contents: dict[str, Any]) -> str:
    """Serialize a vector file the same way every time."""
    return json.dumps(contents, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    """Write every vector file."""
    (VECTORS_DIR / "canonical.json").write_text(render(build_canonical()), encoding="utf-8")
    (VECTORS_DIR / "checkpoint.json").write_text(render(build_checkpoints()), encoding="utf-8")
    (VECTORS_DIR / "sum_tree.json").write_text(render(build_sum_tree()), encoding="utf-8")


if __name__ == "__main__":
    main()
