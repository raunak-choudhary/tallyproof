# Running Tallyproof on AWS

Tallyproof runs on one laptop with open-source components, and nothing in this repository is deployed to AWS. Each component does have a direct AWS counterpart, though, and this page shows how the system would map onto AWS and what would change at production scale. Service details were checked against AWS documentation in October 2026.

## Component mapping

| Local component | AWS equivalent | What changes |
|---|---|---|
| Spark in local mode | AWS Glue jobs or Amazon EMR | The same PySpark code, run on a cluster instead of three local cores |
| Deequ checks | Deequ on Glue or EMR, or AWS Glue Data Quality, which is built on Deequ | The constraints carry over |
| Downloaded archives (bronze layer) | S3, with Object Lock for the raw files | The source-file hashes in the ledger stay the same |
| Parquet and Iceberg data files on local disk | Amazon S3 data lake | Same layout and partitioning |
| Iceberg with a local SQL catalog | Amazon S3 Tables, or Iceberg tables in the Glue Data Catalog | Only the catalog changes |
| DuckDB for ad hoc queries | Amazon Athena | Minor SQL dialect differences |
| Redpanda (Kafka API) | Amazon MSK | Same client code, IAM authentication, partitions sized from the load test |
| Redpanda Schema Registry | AWS Glue Schema Registry | Schemas are already JSON Schema draft-07 with internal references only, which Glue accepts |
| PostgreSQL 16 with pgvector | Aurora PostgreSQL with pgvector | Same migrations, a read replica for the analyst role, pgAudit for database-level auditing |
| Ed25519 key in a local file | AWS KMS asymmetric key, spec `ECC_NIST_EDWARDS25519`, algorithm `ED25519_SHA_512` with raw messages | The private key never leaves KMS. The pre-hash variant must be avoided, because standard verifiers reject its signatures |
| Witness copies and external timestamps | An S3 bucket with Object Lock in compliance mode, alongside the external timestamps | Not even the root account can delete or overwrite locked versions. AWS reports an assessment for SEC 17a-4, CFTC, and FINRA record keeping |
| Redis | Amazon ElastiCache, Valkey or Redis OSS engine | No code change |
| Workers | ECS Fargate services, scaled by consumer group | Health checks through `/readyz` |
| Django API | ECS Fargate behind an Application Load Balancer | Same container |
| Scheduled jobs | EventBridge Scheduler triggering Step Functions, or Amazon MWAA | |
| Logs and traces | CloudWatch and the AWS Distro for OpenTelemetry | The X-Ray SDKs reach end of support in February 2027, so instrumentation uses OpenTelemetry only |
| Static demo site | S3 and CloudFront | |

## The QLDB gap

Amazon QLDB reached end of support on 31 July 2025. AWS recommends Aurora PostgreSQL in its place, and its migration guidance notes that Aurora PostgreSQL doesn't keep a permanent, immutable record of changes; that history has to be generated and stored outside the database. Tallyproof is a working version of that pattern: Postgres for the data, an RFC 9162 Merkle log for the history, checkpoints that KMS could sign, and witnessed copies in storage nobody can rewrite. Sources are in [references.md](references.md).

## What changes at production scale

- **The single log writer is the first bottleneck.** The fix is a log per partition with a top-level log of shard heads, signed both per shard and globally.
- **Proofs would be served as static tiles** from S3 and CloudFront, using the transparency.dev tile layout, so proof reads never touch Aurora.
- **Effectively-once processing doesn't change.** Offsets are still stored in the same Aurora transaction as the ledger writes.
- **Batch jobs scale out** from one laptop to a Glue or EMR cluster with no code changes. The single-machine resource limits become cluster sizing.
- **LLM costs** stay bounded by per-team budgets, either through Amazon Bedrock or a direct API, with the response cache in ElastiCache.

An infrastructure-as-code sketch of this layout may be added later. It would never be deployed from this repository and would contain no account identifiers.
