# ADR-0008: Effectively-once ingestion with Bloom fast path

- Status: Proposed (MC-01)
- Date: 2026-10-26
- Zone: Open (design of a locked requirement)

## Context

The brief says ingestion deduplicates with a Bloom filter for "idempotent, effectively exactly-once processing". A Bloom filter alone cannot do that: false positives would silently drop real payments, which is a correctness bug in a ledger.

## Decision

1. **The database is the authority.** `UNIQUE (idempotency_key)` on `ledger_event`.
2. **The Bloom filter is a fast path, used only for its guarantee.** A Bloom filter has no false negatives. "Definitely not seen" records are bulk-inserted without conflict handling. "Maybe seen" records take the slow path: `INSERT ... ON CONFLICT DO NOTHING`, conflicts logged to `dedupe_rejection`.
3. **Offsets in the same transaction.** `consumer_offset` is updated in the same Postgres transaction as the ledger rows and outbox rows. On restart, the consumer seeks to the stored offset. Kafka delivery is at-least-once; the idempotent, transactional sink makes processing effectively-once.
4. **Bloom state** is per partition (events are keyed by `account_id`, so duplicates share a partition), sized from `DEDUPE_EXPECTED_ITEMS` and `DEDUPE_TARGET_FPR`, and rebuilt from the database on startup. If the fast path ever hits a unique violation, the batch falls back to the slow path and a counter is incremented.

## Why keep the Bloom filter at all?

It decides which records can skip conflict handling. At high duplicate-free volume, most records go through a bulk path; only the "maybe" fraction (true duplicates plus FPR) pays for conflict checks. The load test reports fast-path share and the throughput difference against an always-slow-path baseline. If the difference is negligible at our scale, we will say so.

## Alternatives

- Kafka transactions (read-process-write) give exactly-once within Kafka only. Our sink is Postgres, so the offset-in-sink pattern is the correct tool.
- Redis SET for dedupe: another stateful dependency, no stronger guarantee than the database.
