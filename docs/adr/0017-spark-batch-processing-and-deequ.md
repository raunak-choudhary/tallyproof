# ADR-0017: PySpark 4.1 for batch processing, with Deequ data quality checks

- Status: Accepted
- Date: 2026-10-27

## Context

The project now processes real public spending data at tens of gigabytes (ADR-0016). The audience is data-platform engineers, whose batch processing runs on Spark (AWS Glue and EMR). The reference machine is an Apple M3 with 8 GB of RAM and about 45 GB of free disk, so the design must be out-of-core and gentle on resources.

## Decision

1. **PySpark 4.1.x** (4.1.3 at time of writing) in local mode, installed into `backend/.venv` via pip-tools like every other dependency. It runs on **OpenJDK 17**, installed keg-only through Homebrew and exposed to project commands only through `JAVA_HOME` in the Makefile.
2. **Data quality with Deequ** (Amazon's open-source library) through **PyDeequ 1.7.0**, which supports Spark 3.5 and Spark 4.1. This is why Spark is pinned to 4.1 and not 4.2: Deequ does not support 4.2 yet. Revisit when it does.
3. **Resource limits:** `local[3]`, driver memory 2 GiB, a small shuffle partition count, spill to local disk. The batch job refuses to start while the container stack is running (`make data-build`), so Spark and the Colima VM never compete for the 8 GB.
4. **Out-of-core input:** each fiscal year arrives as a zip of about 2 GB CSV members. Members are extracted one at a time, processed into Parquet, and deleted. Raw zips are kept as the immutable bronze layer.

## What runs on Spark

| Job | Input | Output |
|---|---|---|
| Bronze to silver | Raw CSV members | Typed, deduplicated, PII-free Parquet partitioned by fiscal year and month; quarantine table with reason codes |
| Data quality | Silver tables | Deequ verification results and a metrics history table; the build fails on any error-level constraint |
| Profiling report | Silver tables | `docs/data/profile-<dataset>.md`: row counts, null rates, distributions, dropped-row counts by reason, committed as evidence |
| Gold events | Silver tables | Conformed event files in event-time order, ready for Kafka replay |
| Batch reconciliation (later) | Silver tables | Full-population reconciliation for comparison with the streaming result |

## Alternatives

- **Polars or DuckDB:** faster and lighter on one laptop, and they would handle this data well. Rejected as the main engine only because Spark is what the target audience runs in production. DuckDB stays as an optional query tool over the Parquet lake.
- **Spark in a container:** no local Java needed, but slower to iterate and it competes for the VM's 3 GiB. Rejected.
- **Great Expectations:** mature, but Deequ is AWS's own tool and runs natively inside Spark.

## Consequences

- Java 17 becomes a system prerequisite, documented in the runbook with its uninstall command.
- CI does not run full-size Spark jobs. It runs the same jobs on a committed sample of about 50k rows, which keeps CI fast and still exercises every transformation and constraint.
- Spark 4.1 versus 4.2 is tracked on the watch list.
