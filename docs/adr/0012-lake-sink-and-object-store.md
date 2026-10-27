# ADR-0012: Parquet lake sink on SeaweedFS (S3 API), promoted to MLP

- Status: Proposed (MC-01)
- Date: 2026-10-26
- Zone: Open (scope change from Nice-to-have, plus tool choice)

## Context

Finance data-platform teams work in S3, Parquet, Iceberg, Glue, Athena. A Postgres-only pipeline undersells the "big data" signal. The brief listed "Parquet + DuckDB cold storage" as Nice-to-have.

## Decision

1. Promote a **lake sink** to MLP: a consumer of `ledger.appended.v1` writes Parquet files partitioned by `event_date` and `event_type` to an S3-compatible bucket, with idempotent file naming by Kafka offset range.
2. Extend **control totals** to the lake: counts and sums per batch must match across topic, ledger, and lake.
3. Keep DuckDB batch analytics and Iceberg tables (pyiceberg SQL catalog) in Nice-to-have.
4. Local object store: **SeaweedFS** (Apache-2.0, S3 API, Object Lock support).

## Why not MinIO

As of 2026-10, the MinIO community repository is archived and marked no longer maintained, the community edition is source-only, and no new official Docker images have been published since October 2025. Garage has no Object Lock. LocalStack now requires an auth token, which is unsuitable for a public repo reviewers clone.

## Risks

SeaweedFS Object Lock completeness is only documented in secondary sources. It will be verified by an integration test before we rely on it in docs. Local Object Lock is a behavioral stand-in; only S3 Object Lock compliance mode gives the real regulatory guarantee (stated plainly).

## Library pins

PyArrow 26.x, DuckDB 1.5.x (2.0 LTS was released five days before this ADR; revisit at RP-2).
