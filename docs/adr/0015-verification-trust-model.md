# ADR-0015: Verification trust model (what the green check actually proves)

- Status: Accepted
- Date: 2026-10-26

## Context

Plan review found three overclaims in the first drafts:
1. "The browser verifies with no trust in the server" was false: the key, checkpoint, and proof all came from the same origin.
2. Proofs covered `canonical_bytes`, but the analyst, reconciliation, and journal read a separate `payload` JSONB column. Tampering the JSONB would show a falsified value next to a green proof.
3. The tamper ladder distinguished levels 1 and 2 using a server-supplied `leaf_hash`, which the client must not trust.

## Decision

### What the browser trusts
- A **release public key pinned in the web build** (fingerprint also in the README). Never a key read from the API or bundle it is verifying.
- The **latest externally witnessed checkpoint**, fetched from a different origin than the API (raw GitHub URL of `witness/`), with its OpenTimestamps proof.

### What every Verify does
1. Canonicalize the event in the browser and hash it (client computes the leaf hash; the server's `leaf_hash` is never used).
2. Walk the audit path to a root; check the served checkpoint's signature with the pinned key.
3. Fetch a **consistency proof** from the served checkpoint to the witnessed checkpoint (or the reverse) and verify it. The UI shows "consistent with witnessed checkpoint #N, timestamped <date>".
4. **Bound-value check:** for every value or field the answer displays from this event, compare it with the field inside the verified canonical bytes. A mismatch fails.

### Storage
- `canonical_bytes` is the only source of truth. `payload` becomes a **STORED generated column** computed from `convert_from(canonical_bytes, 'UTF8')::jsonb`. Analyst views read `payload`, so altering what the analyst sees requires altering `canonical_bytes`, which breaks the leaf. Step 4 above covers the remaining case (a superuser dropping and recreating the column).
- Policy documents are leaves too. Quote checks run against the verified document leaf bytes, never against a mutable `body` column.
- The journal and reconciliation breaks are **derived** state. They are labeled "derived, re-derivable from verified events" in the UI and never carry a "verified" badge by themselves.

### Tamper ladder, corrected
| Level | Attacker | Fails at |
|---|---|---|
| 1 | Edits the stored event (any column) | Bound-value check or leaf recompute vs audit path (root mismatch) |
| 2 | Edits event and rebuilds tree, cannot sign | Checkpoint signature with pinned key |
| 3 | Edits, rebuilds, re-signs with a stolen key | Consistency proof against the externally witnessed checkpoint |
| 4 | As 3, acting before the next external timestamp | Not detectable; window = `WITNESS_INTERVAL_SECONDS` |

The public demo shows levels 1 to 3 in the browser. Level 3 uses a **separate, published demo key** in a clearly labeled demo log, so the demo never needs the real release key and nothing is faked. Level 4 is explained, not demonstrated.

### Reproducibility
- Live logs are intentionally non-deterministic (consumer interleaving). Witnesses are scoped per log identity: `origin + key_id + genesis hash`. `make verify-witness` checks only checkpoints for the local log identity.
- The replay bundle is built in **deterministic mode**: single consumer, merge by `(partition, offset)`, seeded ULIDs. Same seed and commit produce the same root, so anyone can rebuild the public demo's log and compare roots.

## Consequences

The claim becomes: **"Your browser trusts only a pinned key and an externally timestamped checkpoint. Everything else is checked."** That claim is true and defensible.

## Implementation notes (2026-10-29)

The browser verifier (`frontend/src/lib/verify/verifyEvent.ts`) checks the checkpoint's signature against the pinned key, the record's canonical form, the leaf hash, and the inclusion proof to the signed root. That catches levels 1 and 2, and the event page demonstrates both: edit an amount, or rebuild the tree around the edit.

The consistency proof against an externally timestamped checkpoint, which catches level 3, runs in `make verify-witness` and the integration tests (`tests/integration/ledger/test_tamper.py`).

## Implementation notes (2026-10-30)

Steps 3 and 4 now run in the browser too. `python -m tallyproof_pipeline.replay_witness --stamp` writes a checkpoint of the replay log below its full size into `witness/replay/` and submits it to the OpenTimestamps calendars; the `.ots` proofs sit beside it. The record page fetches that file from `NEXT_PUBLIC_WITNESS_URL`, which the GitHub Pages build points at the raw file on raw.githubusercontent.com at the commit being published, so the witness comes from a different origin than the site. The verifier checks the witnessed note against the pinned key and verifies a consistency proof from the witnessed root to the signed root; a history rewritten and re-signed with the key fails there even though every other check passes. The record page also prints the record's type, amount, and date into its HTML at build time, and the verifier compares each with the verified bytes.

What remains outside the browser: it can't check the OpenTimestamps proof against Bitcoin by itself. Anyone can, with `ots verify` on the files in `witness/replay/`. On the live page the witness for the live log isn't published anywhere public, so that page still checks levels 1 and 2 only.
