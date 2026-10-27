# ADR-0012: Parquet lake on SeaweedFS (S3 API)

- Status: Accepted
- Date: 2026-10-26

## Context

Finance data-platform teams work in S3, Parquet, Iceberg, Glue, Athena. A Postgres-only pipeline undersells the "big data" signal. Early plans treated Parquet storage as optional. The data pipeline ([ADR-0016](0016-real-public-data-sources.md)) now writes the full cleaned dataset to this lake as well.

## Decision

1. Add a **lake sink**: a consumer of `ledger.appended.v1` writes Parquet files partitioned by `event_date` and `event_type` to an S3-compatible bucket, with idempotent file naming by Kafka offset range.
2. Extend **control totals** to the lake: counts and sums per batch must match across topic, ledger, and lake.
3. Keep DuckDB batch analytics and Iceberg tables (pyiceberg SQL catalog) as later work.
4. Local object store: **SeaweedFS** (Apache-2.0, S3 API, Object Lock support).

## Why not MinIO

As of 2026-10, the MinIO community repository is archived and marked no longer maintained, the community edition is source-only, and no new official Docker images have been published since October 2025. Garage has no Object Lock. LocalStack now requires an auth token, which is unsuitable for a public repo reviewers clone.

## Risks

SeaweedFS Object Lock completeness is only documented in secondary sources. It will be verified by an integration test before we rely on it in docs. Local Object Lock is a behavioral stand-in; only S3 Object Lock compliance mode gives the real regulatory guarantee (stated plainly).

## Library pins

PyArrow 26.x, DuckDB 1.5.x (2.0 LTS was released five days before this ADR; revisit later).
