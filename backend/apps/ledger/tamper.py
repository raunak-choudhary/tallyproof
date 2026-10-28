"""Deliberate tampering, for demonstrating which check catches each level (local only).

The levels follow docs/architecture.md, tamper detection:

1. Edit a stored event, keeping the row internally consistent (bytes, leaf hash,
   columns). The signed root no longer matches: proofs fail, the checkpointer
   refuses to sign, and the witness check fails.
2. Also write the rebuilt root into the newest checkpoint, keeping its old
   signature. The signature check against the pinned key fails.
3. Also re-sign that checkpoint with the real key, as a thief would. Signatures
   pass, but the log no longer matches the externally timestamped witness copy.
4. The same before the next external timestamp: not detectable, so not offered.

Every function takes an open connection as the owner role and changes rows the
application role can't touch; a backup of each changed row is returned so the
demo can be undone.
"""

import json
import socket
from typing import Any

import psycopg

from tallyproof_core.canonical import canonicalize
from tallyproof_core.checkpoint import Checkpoint, Signer
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.log_tree import LogTree

LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class TamperRefusedError(RuntimeError):
    """The safety checks did not pass."""


def check_safe(enabled: bool, host: str) -> None:
    """Refuse unless tampering was explicitly enabled against a loopback database."""
    if not enabled:
        raise TamperRefusedError("set DEMO_TAMPER_ENABLED=true to run the tamper demo")
    if host not in LOOPBACK and socket.gethostbyname(host) not in LOOPBACK:
        raise TamperRefusedError(f"the database at {host} is not on loopback; refusing")


def _with_triggers_off(
    conn: psycopg.Connection[Any], table: str, sql: str, params: list[Any]
) -> None:
    conn.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
    try:
        conn.execute(sql, params)
    finally:
        conn.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")


def edit_event(conn: psycopg.Connection[Any], event_id: str, amount: str) -> dict[str, Any]:
    """Level 1: change an event's amount, recomputing its leaf hash so the row stays consistent."""
    row = conn.execute(
        "SELECT canonical_bytes, leaf_hash FROM ledger_event WHERE public_id = %s", [event_id]
    ).fetchone()
    if row is None:
        raise TamperRefusedError(f"no event {event_id}")
    original, original_hash = bytes(row[0]), bytes(row[1])
    document = json.loads(original)
    document["payload"]["amount"] = amount
    edited = canonicalize(document)
    _with_triggers_off(
        conn,
        "ledger_event",
        "UPDATE ledger_event SET canonical_bytes = %s, leaf_hash = %s WHERE public_id = %s",
        [edited, leaf_hash(edited), event_id],
    )
    return {
        "event_id": event_id,
        "canonical_hex": original.hex(),
        "leaf_hash_hex": original_hash.hex(),
    }


def _tree(conn: psycopg.Connection[Any]) -> LogTree:
    tree = LogTree()
    for (leaf,) in conn.execute("SELECT leaf_hash FROM ledger_event ORDER BY leaf_index"):
        tree.append(bytes(leaf))
    return tree


def rebuild_checkpoint(
    conn: psycopg.Connection[Any], signer: Signer | None = None
) -> dict[str, Any]:
    """Level 2 (no signer) or 3 (signer): put the rebuilt root into the newest checkpoint."""
    batch = conn.execute(
        "SELECT id, tree_size, root_hash, checkpoint_note FROM ledger_batch"
        " ORDER BY tree_size DESC LIMIT 1"
    ).fetchone()
    if batch is None:
        raise TamperRefusedError("there is no checkpoint to forge yet")
    batch_id, size, root, note = batch
    new_root = _tree(conn).root(size)
    forged = Checkpoint.from_note_text(note.split("\n\n")[0] + "\n")
    forged = Checkpoint(forged.origin, size, new_root)
    if signer is None:  # keep the old signature line: the signature no longer covers the text
        signature = note.split("\n\n", 1)[1]
        new_note = f"{forged.note_text()}\n{signature}"
    else:
        new_note = signer.sign_checkpoint(forged)
    _with_triggers_off(
        conn,
        "ledger_batch",
        "UPDATE ledger_batch SET root_hash = %s, checkpoint_note = %s WHERE id = %s",
        [new_root, new_note, batch_id],
    )
    return {"batch_id": batch_id, "root_hash_hex": bytes(root).hex(), "checkpoint_note": note}


def restore(conn: psycopg.Connection[Any], backup: dict[str, Any]) -> None:
    """Undo a tamper run from its backup."""
    if "event" in backup:
        event = backup["event"]
        _with_triggers_off(
            conn,
            "ledger_event",
            "UPDATE ledger_event SET canonical_bytes = %s, leaf_hash = %s WHERE public_id = %s",
            [
                bytes.fromhex(event["canonical_hex"]),
                bytes.fromhex(event["leaf_hash_hex"]),
                event["event_id"],
            ],
        )
    if "checkpoint" in backup:
        batch = backup["checkpoint"]
        _with_triggers_off(
            conn,
            "ledger_batch",
            "UPDATE ledger_batch SET root_hash = %s, checkpoint_note = %s WHERE id = %s",
            [bytes.fromhex(batch["root_hash_hex"]), batch["checkpoint_note"], batch["batch_id"]],
        )
