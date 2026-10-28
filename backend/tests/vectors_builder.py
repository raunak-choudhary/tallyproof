"""Build the shared cross-language test vectors from the Python core.

The browser verification library must reproduce every value in these files.
Run ``make vectors`` after changing canonicalization or hashing; a unit test
fails if the committed files no longer match what this builder produces.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from tallyproof_core.canonical import MAX_SAFE_INTEGER, canonicalize
from tallyproof_core.hashing import leaf_hash

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


def render(contents: dict[str, Any]) -> str:
    """Serialize a vector file the same way every time."""
    return json.dumps(contents, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    """Write every vector file."""
    (VECTORS_DIR / "canonical.json").write_text(render(build_canonical()), encoding="utf-8")


if __name__ == "__main__":
    main()
