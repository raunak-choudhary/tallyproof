# 03. Tech Stack

> Versions verified live on 2026-10-26 against PyPI, npm, Docker Hub, and official docs. Full evidence: `docs/research/stack-versions-2026-10.md`. Exact pins live in `requirements*.txt` and `pnpm-lock.yaml`; this table records intent. Patch versions move; majors here are decisions.

## Backend

| Area | Choice | Version line | Why |
|---|---|---|---|
| Language | Python | 3.12 | Strong default; all libraries support it |
| Framework | Django LTS | 5.2.x | ADR-0004; supported to April 2028 |
| API | Django REST Framework + drf-spectacular | 3.18 / 0.30 | OpenAPI from code |
| Realtime | Channels + channels-redis + Daphne | 4.3 / 4.3 / 4.2 | WebSockets (shared rule: no polling) |
| Kafka client | confluent-kafka | 2.16 | librdkafka bundled, arm64 wheels |
| DB driver | psycopg | 3.3 | Async capable, COPY support for fast path |
| Config | pydantic-settings | 2.16 | Typed, fail fast |
| Schemas | pydantic | 2.14 | JSON Schema export (draft-07 target, ADR-0002) |
| Logging | structlog | 26.1 | JSON logs, correlation IDs |
| Canonical JSON | rfc8785 | 0.1.x | ADR-0010 |
| Crypto | cryptography | 50.x | Ed25519 |
| SQL parsing | sqlglot | 30.x (pin exact, releases often) | AST guard |
| Vectors | pgvector (ext 0.8.7, py 0.5) | | Django integration |
| Embeddings | sentence-transformers + BAAI/bge-small-en-v1.5 | 6.2 | 384 dims, CPU friendly, MIT |
| LLM SDK | anthropic | 2.x | Model IDs from env only |
| Batch processing | pyspark | **4.1.x** (4.1.3) | ADR-0017; pinned below 4.2 because PyDeequ supports Spark 3.5 and 4.1 only |
| Data quality | pydeequ (Amazon Deequ) | 1.7.0 | ADR-0017; Deequ constraints and metrics history |
| Java runtime | OpenJDK 17 (Homebrew `openjdk@17`, keg-only) | 17.0.21 | Spark 4.x requires Java 17 or newer; scoped to project commands via `JAVA_HOME` |
| Lake | pyarrow | 26.x | Parquet; Iceberg tables in MLP (E-508) |
| Analytics (Nice) | duckdb | 1.5.x (not 2.0 yet) | 2.0 LTS is days old; revisit at RP-2 |

## Testing and quality (Python)

pytest 9, pytest-django 4.14, hypothesis 6.x, testcontainers 4.15 (Redpanda image pinned explicitly, import from `testcontainers.community.kafka`), coverage, ruff 0.17 (pinned exact), mypy 2.4 strict + django-stubs 6.1, pip-tools 7.6, pre-commit 4.7, conventional-pre-commit 4.4 (commit message lint without Node), gitleaks 8.30, pip-audit.

## Infrastructure (local)

| Component | Image |
|---|---|
| Redpanda | `docker.redpanda.com/redpandadata/redpanda:v26.2.6` |
| Redpanda Console | `docker.redpanda.com/redpandadata/console:v3.13.1` |
| Postgres + pgvector | `pgvector/pgvector:0.8.7-pg16-trixie` |
| Redis | `redis:7.4` line (pin at T-104) |
| Object store (MLP) | SeaweedFS 4.x (ADR-0012) |
| Container runtime | Colima (CLI only, dedicated `tallyproof` profile: 2 CPUs, 3 GiB, 25 GiB disk). No Docker Desktop (owner decision) |

PostgreSQL 16 kept (strong default). It is supported to November 2028, matches Django 5.2's window, and is available on Aurora PostgreSQL.

## Frontend

| Area | Choice | Version line | Note |
|---|---|---|---|
| Framework | Next.js App Router | 16.4 | Static export for replay (ADR-0005) |
| UI runtime | React | 19.3 | |
| Language | TypeScript | **6.0.x pinned** | TS 7.0 (Go compiler) is `latest` but typescript-eslint 8 only supports < 6.1 |
| Styling | Tailwind CSS v4 | 4.3 | CSS-first config, tokens as CSS variables |
| Components | shadcn/ui CLI | 4.x | Copy-in components, Radix primitives |
| Motion | `motion` (import `motion/react`) + GSAP | 14.6 / 3.15 | GSAP is free incl. plugins under its own no-charge license (not OSI); acceptable for this use |
| Data | TanStack Query | 5.x | |
| Crypto | @noble/ed25519, @noble/hashes | 3.2 / 2.4 | Identical behavior across browsers (ADR-0007) |
| Canonical JSON | canonicalize | 5.1 | ADR-0010 |
| Tests | Vitest 5, Playwright 1.64 | | |
| Lint/format | ESLint **10** (9 is EOL since 2026-08-06), typescript-eslint 8.72, Prettier 3.9 | | |
| Package manager | pnpm 10 | | Lockfile committed (REQ-ENV-03) |

## CI, docs, release

| Area | Choice | Note |
|---|---|---|
| CI | CircleCI `version: 2.1` | Machine executor for Testcontainers; schedule triggers for nightly; `pipeline.trigger.type` not `trigger_source` |
| Releases | release-please via minimal GitHub Action | ADR-0011 |
| Dependencies | Dependabot (pip, npm, docker, github-actions) | CI check recompiles pip-tools and diffs to catch churn |
| Docs site | MkDocs Material 9.8 + mkdocstrings | Material is in maintenance mode; config kept Zensical-compatible (plain `mkdocs.yml`, no Material-only plugins) so we can switch without rework. Decision logged, no ADR needed because the default is kept |

## Watch list (decisions to revisit at RP-2)

- DuckDB 2.0 adoption.
- TypeScript 7 once typescript-eslint supports it.
- gitleaks maintenance status (successor Betterleaks); gitleaks remains the brief's named tool.
- Channels release cadence.
