# ADR-0002: Redpanda as the local Kafka-compatible broker

- Status: Proposed (MC-01)
- Date: 2026-10-26
- Zone: Strong default (confirmed)

## Context

The brief locks Kafka-compatible streaming. Reviewers must be able to run the full stack with one command and no cloud account.

## Decision

Use Redpanda `v26.2.6` (pinned by tag and digest) and Redpanda Console `v3.13.1` in Docker Compose, with `confluent-kafka` 2.16.x as the Python client. Use Redpanda's built-in Schema Registry with JSON Schema (supported since 24.2).

## Reasons

- Single binary, no ZooKeeper or KRaft controller quorum to configure, fast startup: good for laptops and CI.
- Kafka API compatible, so the same client code runs against Amazon MSK (`15-aws-reference-architecture.md`).
- Built-in Schema Registry and Console give a visible, inspectable pipeline for reviewers.
- `testcontainers` ships a `RedpandaContainer` (import from `testcontainers.community.kafka`).

## Constraints discovered during research

- `RedpandaContainer` defaults to an old image (v23.1) without JSON Schema registry support. Always pass the pinned image.
- Cross-subject `$ref` is not supported in Redpanda's JSON Schema registry. AWS Glue Schema Registry accepts only drafts 4, 6, and 7. Therefore event schemas are **JSON Schema draft-07 with internal `$defs` only**, so they port to Glue unchanged.

## Alternatives

- Apache Kafka (KRaft) in Docker: closest to MSK, heavier and slower to start.
- Kinesis via LocalStack: LocalStack now requires an auth token, which is a bad fit for a public repo.
