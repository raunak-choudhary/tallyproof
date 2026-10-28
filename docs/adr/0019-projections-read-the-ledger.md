# ADR-0019: Derived state is projected from the ledger, not consumed from Kafka

- Status: Accepted
- Date: 2026-10-28

## Context

The first architecture had reconciliation and the journal consume `ledger.appended.v1` from Kafka. Building it showed two problems. Kafka delivers at least once, so every consumer would need its own deduplication and offset storage next to its output. And the derived tables live in the same Postgres database as the ledger, so a round trip through the broker adds a failure point without adding anything.

## Decision

Each derived view is a projection that reads the ledger directly, in leaf-index order, starting after its cursor in the `projection_cursor` table. It writes its rows and moves its cursor in one transaction. The projections are `journal` (ADR-0013), `reconciliation`, and `appended`, which writes one outbox row per event for the relay to publish.

Projections wait on the `ledger_appended` notification that ingestion sends on commit, so they don't poll. A projection that fails on an event stops at that event without affecting the others; its cursor hasn't moved, so it retries from the same place.

Kafka is still used for what leaves the database: the outbox relay publishes appended events, breaks, and checkpoints, and the live stream and any outside consumer read those topics.

## Reasons

- Exactly-once output with no extra machinery: the cursor and the rows commit together.
- Rebuilding a view is clearing its rows and its cursor. The result is identical, which a test checks.
- Projections process the log in leaf order, the same order proofs use, so their results don't depend on Kafka partitioning.

## Alternatives considered

- Kafka consumers storing offsets with their output, as ingestion does. It works, but it repeats ADR-0008's machinery for every view.
- Database triggers that write derived rows during ingestion. That couples ingestion latency to every rule and makes a slow rule block appends.

## Consequences

- One worker (`make project`) runs every projection. It's a single writer per view, which is plenty at this scale; projections could be split across workers later because each has its own cursor.
- The `ledger.appended.v1` topic now feeds the live stream and outside consumers, not the journal or reconciliation.
