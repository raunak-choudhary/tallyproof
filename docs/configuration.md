# Configuration

Every setting comes from environment variables, loaded through one typed settings module, `backend/config/env.py`, built on pydantic-settings. If a required variable is missing, startup stops and names it. Each process checks only the secrets it actually uses, so the API never needs, and can't start with, the private signing key.

`.env.example` lists every variable the code reads today, with a short comment. Copy it to `.env`, which git ignores, and fill in the secrets. The values shown here are defaults or examples, never real secrets. Rows marked *planned* belong to work that hasn't been built yet; nothing reads them until it is.

## Application and API

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | yes | `config.settings.local` | One of `base`, `local`, `test`, `ci` |
| `DJANGO_SECRET_KEY` | yes | | Django signing key |
| `DJANGO_DEBUG` | no | `false` | |
| `DJANGO_ALLOWED_HOSTS` | yes | | Comma separated |
| `CORS_ALLOWED_ORIGINS` | yes | | The web app's origin |
| `DATA_CLASSIFICATION` | yes | | Must be `public-no-pii`, or the API refuses to start |
| `DJANGO_SECURE_SSL_REDIRECT` | no | `false` | Redirect HTTP to HTTPS and mark cookies secure. Turn on wherever the API is served over HTTPS |
| `DJANGO_HSTS_SECONDS` | no | `0` | Strict-Transport-Security max age. Preload stays off on purpose |
| `TRUSTED_PROXY_COUNT` | no | `0` | Reverse proxies to trust when finding a client's IP |
| `API_THROTTLE_ANON_READS` | no | `300/min` | Rate limit for read endpoints |
| `API_THROTTLE_ANON_QUERIES` | no | `10/min` | Rate limit for asking the analyst questions, per client IP |
| `API_BASE_URL` | no | `http://127.0.0.1:8000` | Where command-line tools such as `make verify-event` reach the API |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `LOG_FORMAT` | no | `json` | `json` for one object per line, or `console` for reading while developing |

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
| `DB_ANALYST_STATEMENT_TIMEOUT_MS` | planned | `3000` | Today the role script sets the analyst's 3 second timeout directly |
| `DB_ANALYST_MAX_ROWS` | no | `1000` | Most records one answer may cite; a question needing more is refused as too broad |

## Kafka and ingestion

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | yes | | |
| `KAFKA_SCHEMA_REGISTRY_URL` | no | `http://127.0.0.1:18081` | Schema registry for `make register-schemas` and compatibility checks |
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
| `WITNESS_EXPORT_PATH` | no | `var/witness/checkpoints.jsonl` | Local witness output, ignored by git |
| `WITNESS_INTERVAL_SECONDS` | no | `3600` | Longest gap before a checkpoint is externally timestamped |
| `WITNESS_OTS_ENABLED` | no | `true` | Timestamp checkpoint hashes with OpenTimestamps |
| `WITNESS_OTS_CALENDARS` | no | the `a` and `b` OpenTimestamps pool calendars | Comma separated calendar URLs |
| `DEMO_TAMPER_ENABLED` | no | `false` | Allows the local tamper demo tool to run |

A checkpoint's key ID isn't configured: it's derived from the key's name and public key, as the C2SP signed-note format specifies, and it appears in `CHECKPOINT_PUBLIC_KEY`.

## Live updates

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `REDIS_URL` | no | `redis://127.0.0.1:6379/0` | The WebSocket channel layer |
| `STREAM_HOST` | no | `127.0.0.1` | Address the WebSocket server listens on |
| `STREAM_PORT` | no | `8001` | Port the WebSocket server listens on |
| `WS_MAX_CONNECTIONS_PER_IP` | no | `5` | Further connections from one IP are refused with code 1013 |
| `WS_CLIENT_BUFFER` | no | `100` | Facts held for one client; past it the oldest are dropped and the client is told how many |
| `WS_MAX_MESSAGE_BYTES` | no | `4096` | Largest WebSocket frame the server accepts |

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
| `DATA_SOURCE_ECFR_API_URL` | for the policy corpus | | Base URL of the eCFR versioner API, where the FAR text comes from |
| `DATA_FISCAL_YEARS` | no | `[2024, 2025]` | Fiscal years to download, as a JSON list; `[2025]` for a single year |
| `DATA_OUTLAY_FISCAL_YEAR` | no | `2024` | Fiscal year of the account-level outlay data; match it to the replayed slice |
| `DATA_OUTLAY_QUARTERS` | no | `[1]` | Quarters of outlay data to download, one generated file each; the server can't build a whole year at once |
| `POLICY_FAR_PARTS` | no | `[2, 4, 32, 43]` | FAR parts kept in the policy corpus |
| `POLICY_CORPUS_DIR` | no | `backend/corpus/far` | Where the committed policy corpus lives |
| `DATA_DOWNLOAD_MAX_MBPS` | no | `20` | Download speed cap |
| `DATA_SCENARIO` | no | `full` | Build size: `smoke` (2,000 events, 2 of each anomaly), `demo` (20,000 and 5), `full` (1,000,000 and 25), or `volume` (15,000,000 and 100) |
| `DATA_REPLAY_SLICE_EVENTS` | no | from the scenario | Events replayed from the lake into Kafka; overrides the scenario |
| `DATA_REPLAY_RATE_PER_SEC` | no | `2000` | Replay speed; raised only for load testing |
| `DATA_TREASURY_POLL_SECONDS` | no | `3600` | How often the live Treasury connector checks for a new daily statement |
| `OVERLAY_SEED` | no | `42` | Seed for the injected anomalies |
| `OVERLAY_PER_ANOMALY` | no | from the scenario | How many of each anomaly type to inject; overrides the scenario |
| `SPARK_MASTER` | no | `local[3]` | Keeps Spark to three cores |
| `SPARK_DRIVER_MEMORY` | no | `2g` | Keeps Spark within the laptop's memory budget |
| `SPARK_SHUFFLE_PARTITIONS` | no | `16` | Kept small for a single machine |
| `SPARK_VERSION` | no | `4.1` | Tells PyDeequ which Deequ build to load |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_LAKE`, `S3_BUCKET_WITNESS` | planned, for the lake | | Local S3-compatible storage. The keys are secrets. Today the lake is Parquet under `data/` |

## Analyst and model provider

The analyst calls its model through one client that speaks the OpenAI chat-completions protocol, which Groq, Google Gemini, OpenRouter, Together, and a local Ollama all serve. The live provider is Groq's free tier with `openai/gpt-oss-120b`: about 1,000 requests a day and 8,000 tokens a minute, enough for one full evaluation a day. Gemini's free tier was tried first but allows only 20 requests a day per model. Switching providers means changing these settings, not code.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LLM_PROVIDER` | no | `fake` | `fake` (scripted answers, no network) or `openai_compatible` |
| `LLM_BASE_URL` | with the real provider | | The provider's OpenAI-compatible endpoint. Groq: `https://api.groq.com/openai/v1`; Gemini: `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `LLM_API_KEY` | with the real provider | | Secret. Sent only in the Authorization header, never logged |
| `LLM_ANSWER_MODEL` | with the real provider | | Model ID for composing answers; never hardcoded |
| `LLM_ROUTER_MODEL` | no | the answer model | Model ID for query specs |
| `LLM_JUDGE_MODEL` | no | the answer model | Model ID for the narrative-faithfulness judge |
| `LLM_REASONING_EFFORT` | no | the provider's default | `none`, `minimal`, `low`, `medium`, or `high`. Thinking counts against the output limit on Gemini and gpt-oss, so a provider's default can cut answers short; `low` is recommended |
| `LLM_TIMEOUT_SECONDS` | no | `30` | Per request |
| `LLM_MAX_RETRIES` | no | `3` | Retries for rate limits and server errors, with backoff |
| `LLM_REQUESTS_PER_MINUTE` | no | `10` | Client-side pacing. On Groq's free tier the binding limit is 8,000 tokens a minute, so evaluations run with `4` |
| `LLM_MAX_INPUT_TOKENS` | no | `8000` | Per request |
| `LLM_MAX_OUTPUT_TOKENS` | no | `1200` | Per request |
| `LLM_RUN_MAX_REQUESTS` | no | `1500` | Per evaluation run; the run stops before passing it |
| `LLM_RUN_MAX_TOKENS` | no | `3000000` | Per evaluation run |
| `LLM_CACHE_DIR` | no | `testdata/llm_cache` | Recorded responses, committed so CI can replay them without a key |
| `ANALYST_MAX_INFLIGHT` | planned | `4` | Concurrent analyst requests |
| `ANALYST_PER_IP_DAILY_TOKENS` | planned | `50000` | Daily token budget per client IP |
| `EMBEDDING_MODEL` | no | `BAAI/bge-small-en-v1.5` | Local embedding model for policy retrieval, run through fastembed; downloads once |
| `EMBEDDING_CACHE_DIR` | no | `var/embeddings` | The downloaded model and cached chunk vectors |

On the free tier, Google may use prompts and responses to improve its products. Prompts carry only public USAspending data and FAR text, so nothing private is exposed; the threat model records this.

## Evaluation (planned)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `EVAL_MAX_USD_PER_RUN` | no | `1.00` | Spending limit per evaluation run |
| `EVAL_THRESHOLDS_PATH` | no | `evals/thresholds.toml` | |

## Frontend

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_PINNED_VERIFIER_KEY` | The one public key the site trusts, compiled into the build. On GitHub Pages it comes from the repository variable `PINNED_VERIFIER_KEY` |
| `NEXT_PUBLIC_API_URL` | API base URL. When set, the home page links the live page at `/live/`; when empty, only the static replay demo is offered |
| `NEXT_PUBLIC_BASE_PATH` | Path the site is served under: empty locally, `/tallyproof` on GitHub Pages |
| `NEXT_PUBLIC_REPLAY_BASE` | Where the replay bundle is served from; empty means `<base path>/replay` |
| `NEXT_PUBLIC_BUILD_COMMIT`, `NEXT_PUBLIC_SOURCE_URL` | Set by the publishing workflow so every page names, and links, the commit it was built from |
| `NEXT_PUBLIC_WS_URL` | planned: WebSocket base URL for live updates in the browser |

The frontend reads its own `frontend/.env.example`, not the repository's `.env`.

## CI secrets

CI needs no secrets today: every job runs on public code and generates any key it needs at runtime. The analyst and evaluation work will add three CircleCI contexts, never configuration files, each restricted to `main` and scheduled pipelines so pull request pipelines receive none of them. Publishing the demo site needs none either: the GitHub Pages workflow uses the built-in token and the public repository variable `PINNED_VERIFIER_KEY` ([ADR-0020](adr/0020-github-pages-for-the-demo-site.md)).

Planned contexts:

- `llm-eval`: `LLM_API_KEY` (a dedicated key with its own limits), `LLM_BASE_URL`, `LLM_ANSWER_MODEL`.
- `bot`: `GITHUB_BOT_TOKEN`, limited to pushing `bot/*` branches and opening pull requests. It can't push to `main`.
- `signing-ci`: the CI signing key. The release key never enters CI.
