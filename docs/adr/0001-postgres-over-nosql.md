# ADR-0001: PostgreSQL over NoSQL for the ledger

- Status: Accepted
- Date: 2026-10-26

## Context

The ledger stores money movements, must enforce integrity, supports reconciliation, and is the target of LLM-generated queries. AWS retired Amazon QLDB (end of support 2025-07-31) and points customers to Aurora PostgreSQL. AWS's own migration guidance states: "Amazon Aurora PostgreSQL does not keep a permanent, immutable record of changes. Instead, that history must be generated as audit data and stored outside of the database." (AWS Database Blog, 18 July 2024; archived links in [references](../references.md).)

## Decision

Use PostgreSQL 16 with pgvector as the system of record. Add tamper evidence ourselves: an append-only event table, an RFC 9162 Merkle log over canonical event bytes, Ed25519-signed checkpoints, and checkpoints exported outside the database (ADR-0007).

## Reasons

1. Multi-row atomic transactions: an event, its leaf, its consumer offset, and its outbox row commit together (ADR-0008).
2. Database-enforced integrity: foreign keys, CHECK constraints, UNIQUE idempotency keys, exact `NUMERIC` money, deferred balanced-entry triggers.
3. Reconciliation is a relational join between payments and invoices.
4. Text-to-SQL is more reliable than LLM-generated NoSQL queries, and SQL is easier to sandbox: AST allowlists, read-only roles, statement timeouts.
5. JSONB keeps raw payload flexibility.
6. It maps directly to Aurora PostgreSQL, the AWS-recommended QLDB replacement, so the project is a working answer to the gap AWS describes.

## Alternatives considered

- **DynamoDB:** wins for massive key-value workloads with fixed access patterns and single-digit-millisecond reads at any scale. Loses here: reconciliation joins, ad hoc analyst queries, and multi-item transactional invariants are awkward.
- **MongoDB:** supports multi-document transactions, so this is not a capability gap. It is a fit gap: sandboxing LLM-generated aggregation pipelines is harder than sandboxing SQL.
- **A ledger database (immudb, Trillian with MySQL):** gives verification for free but hides exactly the data-structure work this project is meant to demonstrate.

## Consequences

- We own the correctness of the Merkle log and signing. Mitigated by property tests and RFC test vectors.
- A single log writer per Postgres instance limits throughput (measured, see `architecture.md` section 9).
