# ADR-0003: Merkle log structure and batching policy

- Status: Accepted
- Date: 2026-10-26

## Context

Events are grouped into Merkle trees, roots are committed, and any event can return an inclusion proof. There are two common shapes:

- **A. Independent per-batch trees, roots hash-chained** (block-header style).
- **B. One append-only log, batches are checkpoints of its growing size** (Certificate Transparency style, RFC 9162).

## Decision

Choose **B**. One global append-only Merkle log. A batch (`bat_`) is the range of leaves added since the previous checkpoint. Closing a batch produces a signed checkpoint over the whole log `[0, tree_size)`.

Batching policy: close when `MERKLE_BATCH_MAX_SIZE` leaves (default 256) have accumulated **or** `MERKLE_BATCH_MAX_AGE_MS` (default 2000) has passed since the batch opened, whichever comes first. Both values are configuration, not code.

Hashing per RFC 9162 section 2.1: leaf = `SHA-256(0x00 || canonical_bytes)`, node = `SHA-256(0x01 || left || right)`, split at the largest power of two smaller than n. Canonical bytes per RFC 8785 (ADR-0010).

## Reasons

- **Consistency proofs.** B lets anyone prove that checkpoint n extends checkpoint m without rewriting history. That is exactly what defeats tamper ladder level 4. In A, the hash chain gives a similar property but with linear-size proofs across many batches.
- **Standard.** RFC 9162 and the C2SP checkpoint format are what transparency logs use in production (Certificate Transparency, Go checksum database, Sigstore Rekor). Interoperability and reviewer recognition.
- **DSA signal.** Inclusion and consistency proofs over a non-power-of-two tree are a real algorithm, not a textbook binary tree.
- **Size-or-time** batching bounds both proof latency (time) and signing overhead (size). Pure size windows starve under low traffic; pure time windows create huge batches under load.

## Consequences

- Proof generation needs interior hashes. Initially computed from stored leaf hashes with a cache of complete subtrees; at scale, persist tiles (transparency.dev tile layout). Measured in the load test.
- Global order is ingestion order, not event time (`architecture.md` section 6.2).
- One log writer at a time (advisory lock). Scale-out path: per-partition logs plus a top-level log of shard heads.

## Benchmark reference

A single-author 2026 preprint reports Merkle construction over 50,000 events in 47 ms with 320 to 512 byte proofs ([references](../references.md)). We will report our own measured numbers side by side and treat the preprint only as a loose reference.
