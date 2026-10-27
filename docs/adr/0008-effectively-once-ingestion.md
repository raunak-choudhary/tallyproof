# ADR-0008: Effectively-once ingestion with Bloom fast path

- Status: Proposed (MC-01)
- Date: 2026-10-26
- Zone: Open (design of a locked requirement)

## Context

The brief says ingestion deduplicates with a Bloom filter for "idempotent, effectively exactly-once processing". A Bloom filter alone cannot do that: false positives would silently drop real payments, which is a correctness bug in a ledger.

## Decision

1. **The database is the authority.** `UNIQUE (idempotency_key)` on `ledger_event`.
2. **Staged insert, never an aborted transaction.** Each batch is copied into a temporary table and moved with `INSERT ... SELECT ... ON CONFLICT DO NOTHING RETURNING`. Conflicts are logged to `dedupe_rejection`.
3. **Contiguous leaf indexes.** Assigned after the insert set is final, from a single-row counter in the same transaction. Rollbacks restore it. No sequences.
4. **Offsets in the same transaction, fenced.** `consumer_offset` is updated in the same transaction with `GREATEST` plus a generation check. On (re)assignment the consumer seeks to the stored offset.
5. **Bloom filter, honestly scoped.** Per partition, rebuilt in `on_assign`, updated as each key is processed (catches duplicates within one poll). Its measurable jobs:
   - Skip the conflict-logging and duplicate-handling path for keys that are definitely new, and report the false-positive rate live as a pipeline metric.
   - Dedupe in the **lake sink**, where S3 objects have no unique constraint and replays would otherwise write duplicate rows.

## Why keep the Bloom filter in ingestion?

Review rightly pointed out that `ON CONFLICT DO NOTHING` costs about the same unique-index probe as a plain insert, so the database-side saving is small. We keep the filter because it is cheap and observable, and we report the measured difference in the load test. If it is negligible, the README says so. Its strongest use is in the lake sink, where nothing else prevents duplicates.

## Alternatives

- Kafka transactions (read-process-write) give exactly-once within Kafka only. Our sink is Postgres, so the offset-in-sink pattern is the correct tool.
- Redis SET for dedupe: another stateful dependency, no stronger guarantee than the database.
