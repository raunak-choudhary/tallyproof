# 13. Configuration

> Every environment variable. Loaded by `backend/config/env.py` (pydantic-settings). Required variables without defaults fail fast at startup with the variable name (REQ-SEC-02). Process-specific secrets are validated only by the process that needs them (per-command settings subclasses), so the API cannot start with, or require, the signing key. `.env.example` mirrors this table (REQ-SEC-03). Values below are examples or defaults, never secrets.

## Backend

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | yes | `config.settings.local` | base, local, test, ci (REQ-SEC-06) |
| `DJANGO_SECRET_KEY` | yes | none | Django signing |
| `DJANGO_DEBUG` | no | `false` | |
| `DJANGO_ALLOWED_HOSTS` | yes | none | Comma separated |
| `CORS_ALLOWED_ORIGINS` | yes | none | Web origin(s) |
| `DB_URL` | yes | none | App role connection |
| `DB_OWNER_URL` | migrations only | none | Owner role for `make migrate`; never given to the API or workers |
| `DB_ANALYST_URL` | yes | none | Read-only analyst role (REQ-SEC-07) |
| `DB_ANALYST_STATEMENT_TIMEOUT_MS` | no | `3000` | |
| `DB_ANALYST_MAX_ROWS` | no | `1000` | |
| `REDIS_URL` | yes | none | Cache + channel layer |
| `KAFKA_BOOTSTRAP_SERVERS` | yes | none | |
| `KAFKA_SCHEMA_REGISTRY_URL` | no | none | Phase 6 schema evolution |
| `KAFKA_TOPIC_EVENTS_RAW` | no | `fin.events.raw.v1` | |
| `KAFKA_TOPIC_EVENTS_DLQ` | no | `fin.events.dlq.v1` | |
| `KAFKA_TOPIC_LEDGER_APPENDED` | no | `ledger.appended.v1` | |
| `KAFKA_TOPIC_CHECKPOINTS` | no | `ledger.checkpoints.v1` | |
| `KAFKA_TOPIC_RECON_BREAKS` | no | `recon.breaks.v1` | |
| `KAFKA_CONSUMER_GROUP_INGEST` | no | `ingest-v1` | |
| `INGEST_MAX_BATCH` | no | `500` | |
| `DEDUPE_EXPECTED_ITEMS` | no | `1000000` | Bloom sizing |
| `DEDUPE_TARGET_FPR` | no | `0.001` | Bloom sizing |
| `MERKLE_LOG_ORIGIN` | yes | none | Checkpoint origin line |
| `MERKLE_BATCH_MAX_SIZE` | no | `256` | ADR-0003 |
| `MERKLE_BATCH_MAX_AGE_MS` | no | `2000` | ADR-0003 |
| `CHECKPOINT_SIGNING_KEY_FILE` | checkpointer only | none | Path to Ed25519 private key file (mounted, gitignored). Never an env var value. Only the checkpointer process gets it (threat model 5.2) |
| `CHECKPOINT_PUBLIC_KEY` | yes | none | Public key served at `/api/v1/log-key`; the API never holds the private key |
| `CHECKPOINT_KEY_ID` | yes | none | Published key identifier with class prefix `dev-`, `ci-`, `rel-` |
| `WITNESS_EXPORT_PATH` | no | `var/witness/checkpoints.jsonl` | Local runs write to a gitignored path; only the published replay log's witness is committed, under `replay/witness/` |
| `WITNESS_INTERVAL_SECONDS` | no | `3600` | Max time before a checkpoint is externally timestamped; equals level 5 exposure window |
| `WITNESS_OTS_ENABLED` | no | `true` | OpenTimestamps anchoring of checkpoint hashes |
| `DATA_CLASSIFICATION` | yes | none | Must be `synthetic`; API refuses to start otherwise |
| `TRUSTED_PROXY_COUNT` | no | `0` | Number of trusted reverse proxies for client IP resolution |
| `ANALYST_MAX_INFLIGHT` | no | `4` | Global concurrent analyst requests |
| `ANALYST_PER_IP_DAILY_TOKENS` | no | `50000` | Per-IP token budget |
| `RECON_AMOUNT_TOLERANCE` | no | `0.00` | |
| `RECON_FX_TOLERANCE` | no | `0.01` | |
| `RECON_LATE_ARRIVAL_WATERMARK_HOURS` | no | `72` | |
| `LLM_PROVIDER` | no | `fake` | `fake`, `anthropic` |
| `ANTHROPIC_API_KEY` | when provider is anthropic | none | Secret (MC-05) |
| `LLM_ROUTER_MODEL` | when provider is anthropic | none | Never hardcoded |
| `LLM_ANSWER_MODEL` | when provider is anthropic | none | Never hardcoded |
| `LLM_MAX_INPUT_TOKENS` | no | `8000` | Per request |
| `LLM_MAX_OUTPUT_TOKENS` | no | `1200` | Per request |
| `LLM_DAILY_USD_CAP` | no | `2.00` | Denial-of-wallet guard |
| `LLM_CACHE_DIR` | no | `.cache/llm` | |
| `EMBEDDING_MODEL` | no | `BAAI/bge-small-en-v1.5` | |
| `EMBEDDING_DIM` | no | `384` | |
| `EVAL_MAX_USD_PER_RUN` | no | `1.00` | |
| `EVAL_THRESHOLDS_PATH` | no | `evals/thresholds.toml` | |
| `API_THROTTLE_ANON_QUERIES` | no | `10/min` | REQ-SEC-10 |
| `API_THROTTLE_ANON_READS` | no | `300/min` | |
| `DEMO_TAMPER_ENABLED` | no | `false` | Local tamper tool guard |
| `LOG_LEVEL` | no | `INFO` | |
| `LOG_FORMAT` | no | `json` | `json` or `console` |
| `GENERATOR_SEED` | no | `42` | Reproducibility |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_LAKE`, `S3_BUCKET_WITNESS` | MLP | none | Lake and witness storage. Secrets |

## Frontend

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_DATA_MODE` | `live` or `replay` |
| `NEXT_PUBLIC_API_URL` | Live mode API base |
| `NEXT_PUBLIC_WS_URL` | Live mode WebSocket base |
| `NEXT_PUBLIC_REPLAY_BASE` | Replay bundle path |

## CI (CircleCI context `<project>-ci`, never in config files, REQ-SEC-05)

Three separate contexts, each restricted to `main` and scheduled triggers by security group (threat model 5.5):

- `llm-eval`: `ANTHROPIC_API_KEY` (dedicated, spend-capped workspace key), `LLM_ROUTER_MODEL`, `LLM_ANSWER_MODEL`.
- `bot`: `GITHUB_BOT_TOKEN` (GitHub App or fine-grained token: `contents:write` on `bot/*` branches, `pull_requests:write`; cannot push to `main`).
- `signing-ci`: CI-only signing key file contents (`ci-` key class). The release key never enters CI.

PR pipelines receive none of these.
