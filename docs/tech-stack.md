# Technology choices

Versions were checked against PyPI, npm, Docker Hub, and the official documentation in October 2026. Exact pins live in `requirements*.txt` and the frontend lockfile. This page records the version line chosen and why.

## Backend

| Area | Choice | Version | Why |
|---|---|---|---|
| Language | Python | 3.12 | Supported by every library used here |
| Web framework | Django LTS | 5.2 | Security support until April 2028, longer than any newer release ([ADR-0004](adr/0004-django-5-2-lts.md)) |
| API | Django REST Framework, drf-spectacular | 3.18, 0.30 | OpenAPI generated from code |
| WebSockets | Channels, channels-redis, Uvicorn, websockets | 4.3, 4.3, 0.54, 17.3 | Live updates without polling. Uvicorn replaced Daphne, whose Twisted dependency had open vulnerabilities ([ADR-0018](adr/0018-uvicorn-for-websockets.md)) |
| WSGI server | gunicorn | 26.2 | Serves the REST API, separately from the WebSocket server |
| Kafka client | confluent-kafka | 2.16 | Bundles librdkafka and ships Apple Silicon wheels |
| Postgres driver | psycopg | 3.3 | Array parameters for batched inserts, and `LISTEN` for waking workers |
| Settings | pydantic-settings | 2.16 | Typed, and fails fast on missing values |
| Schemas | pydantic | 2.14 | Exports JSON Schema draft-07, registered in the Redpanda schema registry with backward compatibility |
| XML parsing | defusedxml | 0.7 | Parses the eCFR policy text without XML entity attacks |
| Logging | structlog | 26.1 | JSON logs with correlation IDs |
| Canonical JSON | rfc8785 | 0.1 | RFC 8785, used by Sigstore ([ADR-0010](adr/0010-canonical-json-rfc8785.md)) |
| Cryptography | cryptography | 50 | Ed25519 |
| SQL parsing | sqlglot | 30 (pinned exactly, since it releases often) | Guards the fallback query path |
| Vector search | numpy, in memory | 2.5 | The policy corpus is about 700 chunks, so cosine similarity in memory beats running a vector index. pgvector stays available in the database image if the corpus grows |
| Embeddings | fastembed with BAAI/bge-small-en-v1.5 | 0.9 | 384 dimensions on the CPU through ONNX. Chosen over sentence-transformers, which needs PyTorch (about 2 GB) on an 8 GB laptop |
| LLM client | requests over the OpenAI chat-completions protocol | 2.34 | No vendor SDK: one small client reaches Gemini, Groq, OpenRouter, Together, or Ollama by settings alone. Model IDs come from configuration |

## Data pipeline

| Area | Choice | Version | Why |
|---|---|---|---|
| Batch processing | PySpark | 4.1 | The engine AWS Glue and EMR run. Held at 4.1 because PyDeequ supports Spark 3.5 and 4.1, not 4.2 ([ADR-0017](adr/0017-spark-batch-processing-and-deequ.md)) |
| Data quality | PyDeequ (Amazon Deequ) | 1.7.0 | Constraint checks and metric history inside Spark |
| Java | OpenJDK 17 from Homebrew, keg-only | 17 | Spark 4 needs Java 17 or newer. It's scoped to project commands through `JAVA_HOME` and never added to the system path |
| Columnar files | pyarrow | 26 | Parquet, with Iceberg tables added later |
| Ad hoc queries | DuckDB | 1.5 | Optional, for exploring the lake. 2.0 is too new to rely on yet |

## Testing and quality

pytest 9, pytest-django 4.14, Hypothesis 6, testcontainers 4.15 (with the Redpanda image pinned, since its default is far older), coverage, ruff 0.17 pinned exactly, mypy 2.4 in strict mode with django-stubs 6.1, pip-tools 7.6, pre-commit 4.7, conventional-pre-commit 4.4 for commit messages, gitleaks 8.30, and pip-audit.

## Local infrastructure

| Component | Image or tool |
|---|---|
| Container runtime | Colima, command line only, with its own `tallyproof` profile capped at 2 CPUs, 3 GiB of memory, and 25 GiB of disk |
| Kafka-compatible broker | `docker.redpanda.com/redpandadata/redpanda:v26.2.6` |
| Broker console | `docker.redpanda.com/redpandadata/console:v3.13.1` |
| Postgres with pgvector | `pgvector/pgvector:0.8.7-pg16-trixie` |
| Redis | `redis:7.4-alpine`, the WebSocket channel layer |
| S3-compatible storage | SeaweedFS 4, since the MinIO community edition is no longer maintained ([ADR-0012](adr/0012-lake-sink-and-object-store.md)) |

PostgreSQL 16 is supported until November 2028, which covers Django 5.2's support window, and it's available on Aurora PostgreSQL.

## Frontend

Installed today:

| Area | Choice | Version | Note |
|---|---|---|---|
| Framework | Next.js App Router | 16.4 | Static export for the public demo ([ADR-0005](adr/0005-replay-mode-public-demo.md)) |
| UI | React | 19.3 | |
| Language | TypeScript | 6.0 | Version 7 is out, but typescript-eslint doesn't support it yet |
| Styling | Tailwind CSS | 4.3 | Design tokens as CSS variables in `styles/tokens.css`; components in the shadcn/ui style (class-variance-authority, clsx, tailwind-merge), copied in by hand |
| Icons | lucide-react | 1.64 | Outline icons; every icon is paired with a word |
| Motion | Motion 14.8; GSAP 3.15 with ScrollTrigger; Lenis 1.3 | | Motion for component state; GSAP and Lenis for the landing story only, loaded lazily on that route |
| Browser tests | Playwright 1.64, axe-core | | Every page at six viewports in both themes: no sideways scroll, WCAG AA checks; runs in `web-checks` |
| Verification | @noble/ed25519, @noble/hashes, canonicalize | 3.2, 2.4, 5.1 | Identical behavior in every browser ([ADR-0007](adr/0007-signed-checkpoints-and-witnessing.md)) |
| Tests | Vitest | 5.0 | |
| Lint and format | ESLint, typescript-eslint, Prettier | 10, 8.72, 3.9 | ESLint 9 reached end of life in August 2026 |
| Package manager | pnpm | 10 | Lockfile committed |

Chosen for the site, added when it's built: shadcn/ui for components, Motion for in-app transitions, GSAP with ScrollTrigger and Lenis for the landing story (GSAP is free, including plugins, under its own license), React Flow for the Merkle tree, Lightweight Charts for time series, TanStack Query for the REST reads (answers, events, proofs) beside the WebSocket feed, and Playwright with axe for browser and accessibility tests.

## CI, documentation, and releases

| Area | Choice | Status | Note |
|---|---|---|---|
| CI | CircleCI | In use | Machine executor for container-based tests, a weekly scheduled trigger for live evaluations |
| Demo site | GitHub Pages through a GitHub Actions workflow | In use | Actions pinned by commit ([ADR-0020](adr/0020-github-pages-for-the-demo-site.md)) |
| Documentation site | MkDocs 1.6 with Material 9.8 and mkdocstrings 1.0 | In use | Built by the same Pages workflow into `/docs/` beside the demo; API pages are read from docstrings without importing the code |
| Dependency updates | Dependabot | In use | Pinned requirements are recompiled with `make deps`; CI doesn't yet check them for drift |
| Releases | release-please action 5.0.0 in a minimal GitHub Actions workflow | In use | Pinned by commit; all building and testing stays on CircleCI ([ADR-0011](adr/0011-release-automation-on-github-actions.md)) |
| Documentation site | MkDocs Material with mkdocstrings | Planned | Material is in maintenance mode, so the configuration will avoid features that would block a later move to Zensical |

## Worth revisiting later

- Spark 4.2, once PyDeequ supports it.
- DuckDB 2.0, once it has had time to settle.
- TypeScript 7, once typescript-eslint supports it.
- gitleaks, whose original author has started a successor project.
