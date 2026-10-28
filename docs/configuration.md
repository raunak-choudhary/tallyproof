# Configuration

Every setting comes from environment variables, loaded through one typed settings module, `backend/config/env.py`, built on pydantic-settings. If a required variable is missing, startup stops and names it. Each process checks only the secrets it actually uses, so the API never needs, and can't start with, the private signing key.

`.env.example` lists every variable below with a short comment. Copy it to `.env`, which git ignores, and fill in the secrets. The values shown here are defaults or examples, never real secrets.

## Application and API

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | yes | `config.settings.local` | One of `base`, `local`, `test`, `ci` |
| `DJANGO_SECRET_KEY` | yes | | Django signing key |
| `DJANGO_DEBUG` | no | `false` | |
| `DJANGO_ALLOWED_HOSTS` | yes | | Comma separated |
| `CORS_ALLOWED_ORIGINS` | yes | | The web app's origin |
| `DATA_CLASSIFICATION` | yes | | Must be `public-no-pii`, or the API refuses to start |
| `TRUSTED_PROXY_COUNT` | no | `0` | Reverse proxies to trust when finding a client's IP |
| `API_THROTTLE_ANON_QUERIES` | no | `10/min` | Rate limit for asking questions |
| `API_THROTTLE_ANON_READS` | no | `300/min` | Rate limit for read endpoints |

## Database

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `POSTGRES_SUPERUSER_PASSWORD` | for the local stack | | Superuser password for the local container; only the role script uses it |
| `DB_OWNER_PASSWORD` | for the local stack | | Password the role script gives `tallyproof_owner` |
| `DB_APP_PASSWORD` | for the local stack | | Password the role script gives `tallyproof_app` |
| `DB_ANALYST_PASSWORD` | for the local stack | | Password the role script gives `tallyproof_analyst` |
| `DB_URL` | yes | | Connection for the application role |
| `DB_OWNER_URL` | for migrations | | Owner role used only by `make migrate`; never given to the API or workers |
| `DB_ANALYST_URL` | yes | | Read-only role for the analyst |
| `DB_ANALYST_STATEMENT_TIMEOUT_MS` | no | `3000` | |
| `DB_ANALYST_MAX_ROWS` | no | `1000` | |
| `REDIS_URL` | yes | | Cache and WebSocket channel layer |

## Kafka and ingestion

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | yes | | |
| `KAFKA_SCHEMA_REGISTRY_URL` | no | | Schema registry for compatibility checks |
| `KAFKA_TOPIC_EVENTS_RAW` | no | `fin.events.raw.v1` | |
| `KAFKA_TOPIC_EVENTS_DLQ` | no | `fin.events.dlq.v1` | |
| `KAFKA_TOPIC_LEDGER_APPENDED` | no | `ledger.appended.v1` | |
| `KAFKA_TOPIC_CHECKPOINTS` | no | `ledger.checkpoints.v1` | |
| `KAFKA_TOPIC_RECON_BREAKS` | no | `recon.breaks.v1` | |
| `KAFKA_CONSUMER_GROUP_INGEST` | no | `ingest-v1` | |
| `INGEST_MAX_BATCH` | no | `500` | Records per poll |
| `DEDUPE_EXPECTED_ITEMS` | no | `1000000` | Bloom filter sizing |
| `DEDUPE_TARGET_FPR` | no | `0.001` | Bloom filter target false-positive rate |

## Ledger, signing, and witnesses

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `MERKLE_LOG_ORIGIN` | yes | | The origin line in every checkpoint |
| `MERKLE_BATCH_MAX_SIZE` | no | `256` | Leaves per batch before it closes |
| `MERKLE_BATCH_MAX_AGE_MS` | no | `2000` | Longest a batch stays open |
| `CHECKPOINT_SIGNING_KEY_FILE` | checkpointer only | | Path to the Ed25519 private key file. Only the checkpointer reads it |
| `CHECKPOINT_PUBLIC_KEY` | yes | | Public key served at `/api/v1/log-key` |
| `CHECKPOINT_KEY_ID` | yes | | Key ID with its class prefix: `dev-`, `ci-`, or `rel-` |
| `WITNESS_EXPORT_PATH` | no | `var/witness/checkpoints.jsonl` | Local witness output, ignored by git |
| `WITNESS_INTERVAL_SECONDS` | no | `3600` | Longest gap before a checkpoint is externally timestamped |
| `WITNESS_OTS_ENABLED` | no | `true` | Timestamp checkpoint hashes with OpenTimestamps |
| `DEMO_TAMPER_ENABLED` | no | `false` | Allows the local tamper demo tool to run |

## Reconciliation

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `RECON_AMOUNT_TOLERANCE` | no | `0.00` | Allowed difference before amounts count as mismatched |
| `RECON_LATE_ARRIVAL_WATERMARK_HOURS` | no | `72` | How long to wait for late events before a period closes |

## Data pipeline

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATA_DIR` | no | `data/` | Downloads and Parquet output, ignored by git |
| `DATA_SOURCE_USASPENDING_FILES_URL` | for downloads | | Base URL of the award data archive |
| `DATA_SOURCE_USASPENDING_API_URL` | for downloads | | Base URL of the USAspending API |
| `DATA_SOURCE_FISCALDATA_API_URL` | for the live feed | | Base URL of the Treasury Fiscal Data API |
| `DATA_FISCAL_YEARS` | no | `2025` | Fiscal years to download; `2024,2025` for the full build |
| `DATA_DOWNLOAD_MAX_MBPS` | no | `20` | Download speed cap |
| `DATA_REPLAY_SLICE_EVENTS` | no | `1000000` | Events replayed from the lake into Kafka |
| `DATA_REPLAY_RATE_PER_SEC` | no | `2000` | Replay speed; raised only for load testing |
| `OVERLAY_SEED` | no | `42` | Seed for the injected anomalies |
| `SPARK_MASTER` | no | `local[3]` | Keeps Spark to three cores |
| `SPARK_DRIVER_MEMORY` | no | `2g` | Keeps Spark within the laptop's memory budget |
| `SPARK_SHUFFLE_PARTITIONS` | no | `16` | Kept small for a single machine |
| `SPARK_VERSION` | no | `4.1` | Tells PyDeequ which Deequ build to load |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_LAKE`, `S3_BUCKET_WITNESS` | for the lake | | Local S3-compatible storage. The keys are secrets |

## Analyst and LLM

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LLM_PROVIDER` | no | `fake` | `fake` or `anthropic` |
| `ANTHROPIC_API_KEY` | with the real provider | | Secret |
| `LLM_ROUTER_MODEL` | with the real provider | | Model ID for query specs; never hardcoded |
| `LLM_ANSWER_MODEL` | with the real provider | | Model ID for composing answers; never hardcoded |
| `LLM_MAX_INPUT_TOKENS` | no | `8000` | Per request |
| `LLM_MAX_OUTPUT_TOKENS` | no | `1200` | Per request |
| `LLM_DAILY_USD_CAP` | no | `2.00` | Daily spending limit |
| `LLM_CACHE_DIR` | no | `.cache/llm` | Response cache |
| `ANALYST_MAX_INFLIGHT` | no | `4` | Concurrent analyst requests |
| `ANALYST_PER_IP_DAILY_TOKENS` | no | `50000` | Daily token budget per client IP |
| `EMBEDDING_MODEL` | no | `BAAI/bge-small-en-v1.5` | |
| `EMBEDDING_DIM` | no | `384` | |

## Evaluation and logging

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `EVAL_MAX_USD_PER_RUN` | no | `1.00` | Spending limit per evaluation run |
| `EVAL_THRESHOLDS_PATH` | no | `evals/thresholds.toml` | |
| `LOG_LEVEL` | no | `INFO` | |
| `LOG_FORMAT` | no | `json` | `json` or `console` |

## Frontend

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_DATA_MODE` | `live` or `replay` |
| `NEXT_PUBLIC_API_URL` | API base URL in live mode |
| `NEXT_PUBLIC_WS_URL` | WebSocket base URL in live mode |
| `NEXT_PUBLIC_REPLAY_BASE` | Path to the replay bundle |

## CI secrets

Secrets live in three CircleCI contexts, never in configuration files. Each context is restricted to `main` and scheduled pipelines, so pull request pipelines receive none of them.

- `llm-eval`: `ANTHROPIC_API_KEY` (a dedicated key with its own spending limit), `LLM_ROUTER_MODEL`, `LLM_ANSWER_MODEL`.
- `bot`: `GITHUB_BOT_TOKEN`, limited to pushing `bot/*` branches and opening pull requests. It can't push to `main`.
- `signing-ci`: the CI signing key. The release key never enters CI.
