# 15. AWS Reference Architecture (mapping, not deployed)

> Added document (not in brief Section 9.1). Reason: the project cannot use AWS accounts, but its reviewers build on AWS. This document shows the production mapping a reviewer would expect, with the decisions that change when moving to AWS. Facts verified 2026-10-26 (`docs/research/stack-versions-2026-10.md` section 6).

## 1. Component mapping

| Local (this repo) | AWS production equivalent | What changes |
|---|---|---|
| Redpanda (Kafka API) | Amazon MSK (Provisioned or Serverless) | Same client code; IAM auth; partitions sized from load test |
| Redpanda Schema Registry (JSON Schema draft-07) | AWS Glue Schema Registry (JSON Schema drafts 4, 6, 7) | Schemas already draft-07 with internal refs only (ADR-0002) |
| PostgreSQL 16 + pgvector | Aurora PostgreSQL with pgvector | Same migrations; read replica for analyst role; pgAudit for DB-level audit |
| Ed25519 key in `.env` | AWS KMS asymmetric key `ECC_NIST_EDWARDS25519`, `ED25519_SHA_512`, `MessageType=RAW` | Private key never leaves KMS; checkpoints are small, well under message limits. Do **not** use the pre-hash variant; standard verifiers reject it |
| Witness file in git + SeaweedFS Object Lock | S3 bucket with Object Lock in **compliance mode** | AWS documents an assessment by Cohasset Associates for SEC 17a-4, CFTC, and FINRA record-keeping environments |
| Parquet on SeaweedFS | Amazon S3 data lake | Same layout and partitioning |
| pyiceberg SQL catalog (Nice) | Amazon S3 Tables or Glue Data Catalog Iceberg tables | Catalog swap only |
| DuckDB (Nice) | Amazon Athena | SQL dialect differences minor |
| Redis | Amazon ElastiCache (Valkey or Redis OSS engine) | No code change |
| Workers (management commands) | ECS Fargate services; consumer groups scale by task count | Health via `/readyz` |
| Django API | ECS Fargate behind ALB, or App Runner | Same container |
| Scheduled jobs (nightly eval, control totals) | EventBridge Scheduler to Step Functions (or MWAA for DAGs) | |
| structlog JSON + OTel (Nice) | CloudWatch Logs and Metrics, ADOT (AWS Distro for OpenTelemetry) | X-Ray SDKs reach end of support 2027-02-25; instrument with OpenTelemetry only |
| Static replay site | S3 + CloudFront | |

## 2. Why this matters: the QLDB gap

QLDB reached end of support on 2025-07-31. AWS recommends Aurora PostgreSQL and states that Aurora PostgreSQL does not keep a permanent, immutable record of changes; that history must be generated and stored outside the database. This project is that pattern: Postgres plus an RFC 9162 Merkle log, KMS-signable checkpoints, and witnessed copies in Object Lock storage.

## 3. What changes at AWS scale (honest notes)

- **Single log writer** becomes the bottleneck first. Plan: per-partition logs with a top-level log of shard heads, checkpoints signed per shard and globally.
- **Proof serving** moves to static tiles on S3 + CloudFront (transparency.dev tile layout), so proof reads never hit Aurora.
- **Exactly-once** pattern unchanged (offsets in Aurora transaction).
- **Cost controls** for the LLM: Bedrock or direct Anthropic API with per-team budgets; cache in ElastiCache.

## 4. Nice-to-have: IaC sketch

E-606 adds an unapplied Terraform or CDK sketch of this layout. It is never deployed from this repo and contains no account IDs.
