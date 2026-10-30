# ADR-0024: A Merkle-sum tree for provable totals

- Status: Accepted
- Date: 2026-10-30

## Context

An answer's citation lists the records behind each number, and the browser checks every one of them against the signed log. That works for a handful of records. An agency's total on the full ledger covers tens of thousands, so today the citation lists the first 1,000 in log order and says how many the total covers ([limitations](../limitations.md)). The reader can check that those 1,000 records are real, but not that the total is their sum plus the rest.

## Decision

Prove totals with a **sorted Merkle-sum tree** built for each signed log size.

### The tree

- One leaf per obligation or outlay in the checkpoint: a key, the amount in cents, and the record's leaf hash in the Merkle log, which ties every leaf to a log proof.
- The key is `(entity, awarding agency, fiscal year, leaf index)`, computed exactly as the analyst's views compute those columns, including the agency taken from the award's first recorded obligation within the same checkpoint (`tallyproof_core/totals.py`). The leaf index makes every key unique.
- Leaves are sorted by key, and the tree has the log's shape (RFC 9162: split at the largest power of two below the size), so the code that walks it is the code that walks the log.
- Every node hashes its children together with its sum, its record count, and its smallest and largest key. Leaves hash with prefix 0x02 and nodes with 0x03, so nothing in the sum tree can pass for a log hash (0x00, 0x01).

### A total proof

Because leaves are sorted, every key under a prefix (`obligations`, then an agency, then a year) sits in one contiguous run. The proof splits the tree into pieces: subtrees entirely inside the run and subtrees entirely outside it, about `2 log n` of them. A subtree piece carries its children's hashes and the values its own hash commits to, so none of its claims can be changed without changing the root. The verifier, in Python and in the browser:

1. rebuilds the root from the pieces, checking at every join it computes that sums and counts add up and that the left side's largest key is no greater than the right side's smallest;
2. compares the root with the signed one;
3. checks that every inside piece's smallest and largest keys carry the prefix, and that the piece ending just before the run and the one starting just after it don't. A server that hid a record at either end of the run, or slipped one in, fails here;
4. adds up the inside pieces. That sum, and the count beside it, is the proven total.

For a million records the proof has about 32 pieces and is 11 KB of JSON. It takes 9 ms to build and under a millisecond to verify.

### What it proves, and what it doesn't

A valid proof shows that the total is exactly what the signed tree says for that prefix. It does not show that the tree was built honestly: that each record sits under the right key with the right amount. That is checked the way the log itself is audited. The tree is a pure function of the checkpoint's records, so anyone with the log can rebuild it and compare roots. The same pinned key signs both, and the same witness scheme applies, so a signer who published a dishonest tree would leave a signed, permanent record of it.

### Which totals

Totals for an entity, an entity and one agency, and an entity, one agency, and one fiscal year. A total filtered any other way, by industry code or by year across every agency, keeps today's labelled sample. A second tree with a different key order would cover more shapes. That is cheap to add later and not needed for the questions the evaluation asks most.

### Signing

The tree's root is signed as its own C2SP signed note with the checkpoint key, naming the log size it was built for. Checkpoint notes are unchanged, so existing witnesses and tools keep working. Building the tree for a million records takes about 9 seconds in Python, so the checkpointer signs it on a slower cadence than checkpoints (every checkpoint while the log is small). An answer that proves a total is pinned to a checkpoint whose totals are signed.

## Alternatives considered

- **One sum tree per group, append only.** Cheap to extend, but a record's agency can change when its award's first record arrives late, which an append-only group can't express.
- **Unsorted sum tree in log order.** Proves the total of a range of positions, which no question asks for.
- **Zero-knowledge range sums.** Far stronger privacy, far more machinery, and the data is public anyway.

## Consequences

- Large totals become provable in the browser without listing their records, and the labelled-sample caveat goes away for the totals above.
- The checkpointer does more work. On the demo's log it's negligible; on a million-record log it's about 9 seconds and 500 MB at each totals signing, which sets the cadence.
- The tree's correctness rests on the same audit as the log. The documentation says so plainly.
