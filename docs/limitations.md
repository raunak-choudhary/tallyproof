# What was scaled down, and how to run the real thing

Tallyproof was built and measured on one laptop: an Apple M3 with 8 GB of memory, where Spark, a
container VM, and the services share the same memory, and on free tiers of the outside services it
uses. Several things were made smaller on purpose so the whole system would run and be measured
there. This page lists every one of them: what the project does today, what the full-scale version
does, what to change, and which AWS service takes the place of each part. The service mapping is
in [Running Tallyproof on AWS](aws-reference-architecture.md); this page is about the cuts.
Measured numbers are in the README and the [data profile](data-profile.md).

Nothing here changes what the proofs cover. A checkpoint over a million events and a checkpoint
over a billion are verified the same way, by the same code in the browser.

## Data

| Today | Why | At full scale | What to change | On AWS |
|---|---|---|---|---|
| The ledger replays a 1,000,000-event slice of 13.1 million cleaned transactions, in arrival order | The slice already exercises every code path, and the database shares a 3 GiB VM with the broker and the cache | Every transaction, both fiscal years, and new ones as USAspending publishes them | Set `DATA_SCENARIO=volume` (15 million events) or `DATA_REPLAY_SLICE_EVENTS`; give Postgres its own machine and disk | Aurora PostgreSQL; the replay producer becomes an ingestion job on ECS reading from S3 |
| Outlays cover one quarter (FY2024 Q1, 1.08 million payments) | Each quarter is a 1 GB server-generated download; USAspending's generator fails for a full year, and four more quarters add nothing the tests don't already exercise | All quarters of both years | Add quarters to the outlay download settings; the silver and gold steps already loop per file | The same download, scheduled by EventBridge into S3 |
| Spark runs in local mode with three cores and 2 GB of driver memory | The laptop | A cluster sized by the data, with the same PySpark and Deequ code | Change `SPARK_MASTER`, `SPARK_DRIVER_MEMORY`, `SPARK_SHUFFLE_PARTITIONS` | AWS Glue or EMR; Glue Data Quality for the Deequ checks |
| Parquet files on the local disk stand in for a data lake. An Iceberg sink is planned with a local SQLite catalog, not an object store | An object-store service beside the VM and Spark doesn't fit in 8 GB | Iceberg tables in an object store with a shared catalog | Point the catalog at S3 and Glue; the table layout stays the same | S3 and the Glue Data Catalog, or S3 Tables |

## Streaming and the ledger

| Today | Why | At full scale | What to change | On AWS |
|---|---|---|---|---|
| One Redpanda broker, one Postgres, one Redis, in a 3 GiB VM | Memory | Three or more brokers, a primary with replicas, a cache cluster | Compose files and connection strings; no code | MSK, Aurora with a read replica for the analyst role, ElastiCache |
| The API and the workers run as host processes, not containers | To keep the VM's memory for the databases | Every process in its own container, scaled by consumer group | The Dockerfiles exist; run them | ECS Fargate services behind an Application Load Balancer |
| One log writer appends every event | The design is simplest with one writer, and one writer sustains the demo load | A log per partition with a top-level log of shard heads, signed per shard and globally | A planned load test will measure the single-writer ceiling; the sharded design is described in the AWS page | The same, on MSK partitions |
| The signing key is a file on disk, and one key signs everything | No hardware module on a laptop | The private key never leaves a key management service; rotation is a new key name in the checkpoint origin | `CHECKPOINT_SIGNING_KEY_FILE` becomes a KMS key identifier; the signer interface stays | AWS KMS, Ed25519 with raw messages |
| OpenTimestamps is the only outside witness, every hour | Free and public; enough to make the tamper window measurable | Two independent witnesses, a shorter interval, and a locked copy of every checkpoint | `WITNESS_INTERVAL_SECONDS`; add a second witness implementation behind the same interface | S3 Object Lock in compliance mode beside OpenTimestamps |
| Proofs are computed by the API from an in-memory tree | A million leaves fit in memory | Proofs served as static tiles so reads never touch the database | A tile exporter, in the transparency.dev layout | S3 and CloudFront |

## The analyst

| Today | Why | At full scale | What to change | On AWS |
|---|---|---|---|---|
| The model is Groq's free tier running `openai/gpt-oss-120b`, paced at a few requests a minute | Free, and enough for one full evaluation a day; Gemini's free tier allowed 20 requests a day | Any provider that serves the OpenAI chat protocol, or a dedicated endpoint, with a budget per team | Five `LLM_*` settings; no code | Amazon Bedrock, or the provider's API, with the response cache in ElastiCache |
| Live evaluations run weekly, not nightly, and a run of every question spans three nights | The free tier allows 1,000 requests and 200,000 tokens a day per model; one full run needs about 500,000 tokens | Nightly, and on every release | A paid tier (a full run costs cents), or a provider with a larger free allowance | The same schedule on a paid tier |
| A total built from more than 1,000 records (`DB_ANALYST_MAX_ROWS`) is answered in full, but its citation lists only the first 1,000 records in log order, labelled with how many the total covers. On the full ledger that's most agency totals | Citing fifty thousand records in one answer isn't useful in a browser | A Merkle-sum tree proves a total without listing the records | Planned as the provable-totals work; the sample label goes away | No change |
| The regulation index is built in memory from the FAR leaves at startup | 700 chunks need no vector database | Chunks and vectors in the database, refreshed as new editions publish | The pgvector extension is already in the image; add the table and the query | Aurora PostgreSQL with pgvector |
| Each question is answered within its HTTP request, about 30 seconds at the median, by two web workers locally | The model's latency on a free tier | Concurrent requests behind an in-flight cap and a per-address token budget, with answers cached by question and checkpoint | Both limits exist (`ANALYST_MAX_INFLIGHT`, `ANALYST_PER_IP_DAILY_TOKENS`), counted per process; a shared cache makes the budget global, and a faster provider shortens the wait | ECS with more tasks; Bedrock provisioned throughput if needed |

## The demo site

| Today | Why | At full scale | What to change | On AWS |
|---|---|---|---|---|
| The public site is static, on GitHub Pages, and verifies a committed bundle of 2,000 real events | Free, never sleeps, and the browser does all the verifying; no server can go down or be tampered with | The same static site in front of a live API | `NEXT_PUBLIC_API_URL` at build time turns on the live pages; the API runs wherever it runs | S3 and CloudFront for the site; the API on ECS |
| There is no public live backend, so the analyst page works only against the local stack. Answering the demo questions from a precomputed bundle is planned | Running a model-backed public endpoint on a free tier invites exhaustion; the project's claims don't depend on it | A rate-limited live endpoint with the in-flight cap and per-address budget | Deploy the API with the limits on; the site switches modes by one setting | The same |

## Everything else is at full scope

The proof format, the canonical bytes, the checkpoint format, the verifier in the browser, the
reconciliation rules, the journal, the query compiler, the SQL guard, the verifier that stops the
model typing numbers, and the evaluation harness are the same code at any size. The measured
numbers in the README come from the sizes above and say so.
