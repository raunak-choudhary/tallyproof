# ADR-0012: Parquet lake on SeaweedFS (S3 API)

- Status: Accepted, amended 2026-10-30 (see below)
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

## Amendment, 2026-10-30: Iceberg on local disk, no object store

The lake was built differently from the plan above, for memory. An object-store service beside the Colima VM and Spark doesn't fit in 8 GB, so:

1. **Iceberg tables, not loose Parquet files.** The sink writes `tallyproof.events` and `tallyproof.dead_letters` with pyiceberg. The catalog is a SQLite file and the warehouse a folder under `data/lake`. Events are partitioned by event type and by month of `occurred_at`, using Iceberg's hidden partitioning, so queries filter on the timestamp and never on a derived column.
2. **No SeaweedFS.** Nothing runs beside the VM. Checkpoints are still witnessed by OpenTimestamps; a locked copy of each one waits for a real S3 bucket with Object Lock ([ADR-0007](0007-signed-checkpoints-and-witnessing.md)).
3. **The sink reads the replay stream, not Kafka.** It runs with Colima stopped, like the Spark jobs, so it reads the same stream the replay publishes: gold events with the invalid records mixed in at their arrival times. Every message ends one way, as in ingestion: appended, refused as a duplicate, or dead-lettered.
4. **Snapshot properties replace offset-named files.** Each commit stores how far into the stream it got as a property of the Iceberg snapshot, written atomically with the rows. A rerun resumes from there. Duplicates are predicted by the same Bloom filter as ingestion, and a "maybe" is checked exactly against the table ([ADR-0008](0008-effectively-once-ingestion.md)).
5. **Control totals compare the stream, the lake, and the gold build.** `make lake-check` recounts the stream on its own, reads the tables back in batches, and requires equal counts and exact decimal sums per event type. It also recomputes every row's leaf hash from its stored canonical bytes. The ledger is not part of the comparison, since it holds a replayed slice and the lake holds the whole stream.

On AWS, the catalog becomes the Glue Data Catalog and the warehouse an S3 bucket, or both become S3 Tables. The table layout and the sink code stay the same; only the catalog configuration changes ([limitations](../limitations.md)).
