# ADR-0007: Signed checkpoints and external witnessing

- Status: Proposed (MC-01)
- Date: 2026-10-26
- Zone: Open (improvement over the brief)

## Context

If the Merkle root is stored only in the same Postgres database as the events, anyone who can edit the events can recompute the root. The proof then proves nothing. This is the first hole a security-minded reviewer will look for.

## Decision

1. Every checkpoint is a C2SP `tlog-checkpoint` signed note (origin, tree size, base64 root) signed with Ed25519. Private key from `.env` (`CHECKPOINT_SIGNING_KEY`), public key published at `/api/v1/log-key`, in the repo, and in the replay bundle.
2. Checkpoints are **witnessed outside the database**:
   - **Independent anchor:** each checkpoint hash is timestamped with OpenTimestamps (Bitcoin-anchored, no account, operator cannot rewrite) and optionally an RFC 3161 timestamp authority. This is the only witness the operator cannot forge; level 4 detection is claimed only for externally timestamped checkpoints.
   - `witness/checkpoints.jsonl` committed to the repo through normal PRs, protected by CODEOWNERS and no-force-push. This is a convenience copy, **not** an independent witness, because the operator controls the repo. Verification fails on non-fast-forward witness history.
   - Included in the replay bundle.
   - MLP: written to a bucket with Object Lock enabled on the local S3-compatible store (SeaweedFS), as a behavioral stand-in for S3 Object Lock compliance mode.
3. `make verify-witness` checks that every witnessed checkpoint is consistent with the current log (consistency proofs).

## Reasons

Closes tamper ladder levels 2 and 3 (numbering per ADR-0015). Mirrors how Certificate Transparency and the Go checksum database work. Maps directly to AWS KMS (`ECC_NIST_EDWARDS25519`, `ED25519_SHA_512` with RAW messages) plus S3 Object Lock in production.

## Residual risk

Level 4: a key holder who rewrites history before the next external timestamp is not detectable. Exposure equals the witness interval. Documented in README and threat model.

## Browser verification

Native WebCrypto Ed25519 is available in current Chrome, Firefox, and Safari, but key-import support differs slightly across engines. We use `@noble/ed25519` for identical behavior in all browsers and in Vitest.
