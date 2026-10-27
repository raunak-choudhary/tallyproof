# Tech Stack Fact Sheet (verified 2026-10-26)

Method: versions and dates pulled live from PyPI JSON API, npm registry, Docker Hub tags API and GitHub releases API on 2026-10-26, plus official docs. Where a claim rests on secondary sources it is marked UNCERTAIN.

Legend: "Date" = release date of the listed version.

---

## 1. Backend (Python 3.12, pip-tools)

### Django

| Series | Latest patch | Date | Mainstream ends | Extended (security) ends | Notes |
|---|---|---|---|---|---|
| 5.2 LTS | 5.2.18 | 2026-10-06 | 2025-12-03 (passed) | April 2028 | Security-only now |
| 6.0 | 6.0.9 | 2026-10-06 | 2026-08-04 (passed) | April 2027 | |
| 6.1 | 6.1.2 | 2026-10-06 | April 2027 | December 2027 | 6.1.0 released 2026-08-05. NOT LTS. Requires Python >= 3.12 |
| 6.2 LTS | not released | planned April 2027 | December 2027 | April 2030 | Last release under the old support policy |

- Confirmed: Django 5.2 extended support ends April 2028.
- Correction to the brief: 6.1 is not an extended-support release. Its security support ends December 2027, before 5.2's. The next LTS is 6.2 (April 2027).
- Django 5.2 supports Python 3.10 to 3.14 (3.14 as of 5.2.8). Python 3.12: yes.
- Django 5.2 supports PostgreSQL 14 and higher. PostgreSQL 16: yes.
- URLs: https://www.djangoproject.com/download/ , https://docs.djangoproject.com/en/5.2/releases/5.2/

### API, realtime

| Package | Version | Date | Django 5.2 compat | URL |
|---|---|---|---|---|
| djangorestframework | 3.18.3 | 2026-10-06 | Yes. Requires django>=5.2 (classifiers 5.2, 6.0, 6.1) | https://pypi.org/project/djangorestframework/ |
| drf-spectacular | 0.30.0 | 2026-07-06 | Yes (classifiers up to 6.0) | https://pypi.org/project/drf-spectacular/ |
| channels | 4.3.2 | 2025-11-20 | Yes (classifiers 4.2, 5.1, 5.2, 6.0) | https://pypi.org/project/channels/ |
| channels-redis | 4.3.0 | 2025-07-22 | Yes (needs channels>=4.2.2, redis>=4.6) | https://pypi.org/project/channels-redis/ |
| daphne | 4.2.3 | 2026-07-21 | Framework-agnostic ASGI server | https://pypi.org/project/daphne/ |

Note: channels has had no release in 11 months. Not abandoned, but slow.

### Streaming client

| Package | Version | Date | Notes |
|---|---|---|---|
| confluent-kafka | 2.16.0 | 2026-10-07 | Ships `cp312-cp312-macosx_11_0_arm64` wheel with bundled librdkafka. No Homebrew librdkafka needed on Apple Silicon. Also manylinux aarch64/x86_64 wheels. No current arm64 issue found. |

URL: https://pypi.org/project/confluent-kafka/

### Core libraries

| Package | Version | Date | Requires Python | Notes / URL |
|---|---|---|---|---|
| pydantic | 2.14.1 | 2026-10-11 | >=3.10 | https://pypi.org/project/pydantic/ |
| pydantic-settings | 2.16.1 | 2026-10-20 | >=3.11 | https://pypi.org/project/pydantic-settings/ |
| structlog | 26.1.0 | 2026-06-06 | >=3.10 | CalVer. https://pypi.org/project/structlog/ |
| sentence-transformers | 6.2.0 | 2026-10-21 | >=3.10 | Major 6 since 2026-08-18. Requires transformers>=5,<6 and torch>=2.2. torch 2.14.1 has cp312 macOS arm64 wheel. https://pypi.org/project/sentence-transformers/ |
| pgvector (python) | 0.5.1 | 2026-10-09 | >=3.10 | Has Django integration (`pgvector.django`). https://pypi.org/project/pgvector/ |
| pgvector (Postgres ext) | 0.8.7 | Docker tags updated 2026-10-01 | n/a | https://github.com/pgvector/pgvector |
| psycopg (v3) | 3.3.6 | 2026-09-18 | >=3.10 | https://pypi.org/project/psycopg/ |
| sqlglot | 30.25.0 | 2026-10-26 | >=3.9 | Releases very frequently. Pin it. https://pypi.org/project/sqlglot/ |
| cryptography | 50.0.2 | 2026-09-30 | >=3.9 | Ed25519 supported (`cryptography.hazmat.primitives.asymmetric.ed25519`). https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/ |
| anthropic (SDK) | 2.3.0 | 2026-10-23 | >=3.10 | Major 2 line. Check migration notes if copying 0.x examples. https://pypi.org/project/anthropic/ |

### Testing and quality

| Package | Version | Date | Notes |
|---|---|---|---|
| hypothesis | 6.170.12 | 2026-10-26 | Requires Python >=3.11 |
| pytest | 9.1.1 | 2026-06-19 | Major 9 since 2025-11-08 |
| pytest-django | 4.14.0 | 2026-08-10 | Classifiers Django 5.2, 6.0 |
| testcontainers (python) | 4.15.0 | 2026-07-24 | See below |
| ruff | 0.17.3 | 2026-10-26/27 | Still 0.x, pin exact |
| mypy | 2.4.0 | 2026-10-01 | Major 2 since 2026-05-06 |
| django-stubs | 6.1.2 | 2026-10-05 | Classifiers Django 5.2/6.0/6.1. `compatible-mypy` extra pins mypy>=1.13,<2.5, so mypy 2.4 is OK |
| pip-tools | 7.6.2 | 2026-10-07 | pip is at 26.2.2 |
| pre-commit | 4.7.0 | 2026-10-12 | Requires Python >=3.11 |
| gitleaks | v8.30.1 | 2026-03-21 | See risk note |
| conventional-pre-commit | 4.4.0 | 2026-02-18 | Python-native commit-msg hook, replaces commitlint without Node |

testcontainers-python facts (verified by unpacking the 4.15.0 wheel):
- Postgres: `testcontainers.postgres.PostgresContainer` (extra `postgres`). Default image `postgres:latest`, so pin `pgvector/pgvector:0.8.7-pg16-trixie` explicitly.
- Redpanda: YES, `RedpandaContainer` exists, in the `kafka` extra. Import path is now `testcontainers.community.kafka`; `testcontainers.kafka` still works but emits a DeprecationWarning in 4.15. It exposes Kafka 9092 and Schema Registry 8081.
- Gotcha: `RedpandaContainer` defaults to `docker.redpanda.com/redpandadata/redpanda:v23.1.13` (ancient, no JSON Schema support in the registry). Always pass the image tag.
- Also has `minio` and `localstack` modules; no Garage or SeaweedFS module (use `DockerContainer` generic).
- URL: https://pypi.org/project/testcontainers/ , https://github.com/testcontainers/testcontainers-python

gitleaks risk (UNCERTAIN, secondary sources): the original author started Betterleaks (https://github.com/betterleaks/betterleaks, stable v1.9.0 on 2026-09-29, v2.0.0-rc.4 on 2026-10-20) after losing admin control of gitleaks; gitleaks is reported feature-frozen with security fixes only. gitleaks still works and still ships `.pre-commit-hooks.yaml` (hook id `gitleaks`). Betterleaks claims config and flag compatibility. Fine to keep gitleaks for a portfolio; mention Betterleaks as the forward path. Source: https://www.bleepingcomputer.com/news/security/betterleaks-a-new-open-source-secrets-scanner-to-replace-gitleaks/

### Embedding model

BAAI/bge-small-en-v1.5: 384 dimensions, about 33.4M parameters (about 130 MB fp32 safetensors), 512 token max, MIT license. Good CPU choice. URL: https://huggingface.co/BAAI/bge-small-en-v1.5 . Use `vector(384)` in pgvector.

### Browser Ed25519

- WebCrypto Ed25519 is now in all three engines: Firefox 129/130 (Aug/Sep 2024, sources disagree on the exact number), Safari 17.0 (2023), Chrome 137 (May 2025). Spec merged into WebCrypto draft Dec 2024. Source: https://blog.ipfs.tech/2025-08-ed25519/ , https://blogs.igalia.com/jfernandez/?p=1913
- UNCERTAIN: a third-party note says Firefox/Safari restrict some raw key import formats. For verify-only in the browser (import raw 32-byte public key, verify signature) native WebCrypto should be fine, but test in all three.
- Fallback / simpler path: `@noble/ed25519` 3.2.0 (2026-08-27, MIT) and `@noble/hashes` 2.4.0 (2026-08-27). `@noble/curves` 2.4.0 is the superset. Audited, zero-dependency. Recommended if you want identical behavior across browsers and Node test runs.

### JSON canonicalization (RFC 8785, JCS)

| Lang | Package | Version | Date | Status |
|---|---|---|---|---|
| Python | `rfc8785` (Trail of Bits) | 0.1.4 | 2024-09-27 | Repo pushed 2026-10-22, used by sigstore. Pure Python, no deps. Recommended. https://github.com/trailofbits/rfc8785.py |
| Python | `canonicaljson` | 2.0.0 | 2023-03-15 | NOT RFC 8785 (Matrix spec canonical JSON). Do not use for JCS |
| TS | `canonicalize` (erdtman) | 5.1.0 | 2026-09-18 | Apache-2.0, authored by an RFC 8785 co-author. Recommended. https://www.npmjs.com/package/canonicalize |
| TS | `json-canonicalize` | 3.0.1 | 2026-09-10 | MIT, alternative |

Cross-language risk: number serialization (ES6 number-to-string) is the usual divergence. Add a shared golden-vector test (the RFC 8785 appendix vectors) run by both pytest and Vitest.

---

## 2. Streaming and data

### Redpanda

| Item | Value |
|---|---|
| Latest stable | v26.2.6 (Docker Hub tag pushed 2026-10-23). GitHub release page lags (shows v26.2.2 2026-08-22) |
| Image | `docker.redpanda.com/redpandadata/redpanda:v26.2.6` (also `redpandadata/redpanda:v26.2.6` on Docker Hub) |
| Support | 26.1 EOL 2027-03-31; 25.3 EOL 2026-11-19 (per docs index). 26.2 EOL not confirmed, likely about 2027-07 (UNCERTAIN) |
| Schema Registry JSON Schema | Yes. Added in 24.2 (24.1 docs list only Avro and Protobuf, 24.2 docs list JSON). Drafts 04, 06, 07, 2019-09, 2020-12 |
| JSON Schema limitation | `$ref` to a schema under a different subject is NOT supported; internal `$defs` refs are fine |
| Console | `docker.redpanda.com/redpandadata/console:v3.13.1` (2026-10-22). v2.8.x line still patched |
| URLs | https://docs.redpanda.com/current/manage/schema-reg/schema-reg-overview/ , https://hub.docker.com/r/redpandadata/redpanda , https://github.com/redpanda-data/console/releases |

### PostgreSQL

| Major | Current minor | Released | EOL |
|---|---|---|---|
| 18 | 18.6 | 2025-09-25 | 2030-11-14 |
| 17 | 17.11 | 2024-09-26 | 2029-11-08 |
| 16 | 16.15 | 2023-09-14 | 2028-11-09 |
| 14 | 14.24 | | 2026-11-12 (next month) |

Source: https://www.postgresql.org/support/versioning/

- PG16 is fine and covers Django 5.2 LTS lifetime (both end around 2028). PG17 buys a year. PG18 is the newest; Aurora PostgreSQL version parity should be checked before choosing 18 for an "AWS-mappable" story.
- pgvector images: `pgvector/pgvector:0.8.7-pg16-trixie` (also `pg16-trixie`, `pg17-trixie`, `pg18-trixie`). Tags now carry a Debian suffix (`-trixie`); the older bare `pg16` tags may still exist but pin the full tag. https://hub.docker.com/r/pgvector/pgvector

### S3-compatible local object store

MinIO status (verified on GitHub): the `minio/minio` repo says "THIS REPOSITORY IS NO LONGER MAINTAINED", it is archived (read-only), community edition is source-only, no new official Docker images since about October 2025 (last tag RELEASE.2025-10-15T17-29-55Z, the CVE fix that was never pushed to Docker Hub). License AGPLv3. Vendor steers users to "AIStor Free" (proprietary free license). Admin console was stripped from CE in May 2025. Conclusion: do not build a new 2026 project on `minio/minio` images. https://github.com/minio/minio

| Option | Latest | Object Lock | Docker Compose fit | Verdict |
|---|---|---|---|---|
| SeaweedFS | 4.51 (2026-10-25), Apache-2.0 | Yes: governance and compliance modes, legal hold, bucket must be created with lock enabled (versioning required). Sources are wiki mirrors/DeepWiki: UNCERTAIN on completeness | Single `weed server -s3` container works | RECOMMENDED if Object Lock demo matters |
| Garage | v2.5.0 (Docker `dxflrs/garage:v2.5.0`, 2026-10-24), AGPLv3 | NO. Feature request #1127 open, partial PR #1470 rejected pending versioning | Lightweight, needs a layout init step | Good store, but fails the WORM requirement |
| LocalStack | 2026.10.3 (CalVer) | Emulated S3 Object Lock API, not real WORM | Since 2026-03-23 single image requires `LOCALSTACK_AUTH_TOKEN` (free Hobby plan exists, non-commercial) | Avoid for an open portfolio repo: forces reviewers to sign up |
| MinIO | archived | Yes, but unmaintained | Old images only | Avoid |

URLs: https://github.com/seaweedfs/seaweedfs , https://garagehq.deuxfleurs.fr/ , https://git.deuxfleurs.fr/Deuxfleurs/garage/issues/1127 , https://blog.localstack.cloud/localstack-single-image-next-steps/

Honest framing for the doc: local Object Lock is a behavioral stand-in; only S3 Object Lock compliance mode on AWS gives the real regulatory guarantee.

### Analytics libs

| Package | Version | Date | Notes |
|---|---|---|---|
| DuckDB | 2.0.0 LTS | 2026-10-21 | Brand-new major with breaking changes, supported to at least Oct 2027. 1.5.x extended to March 2027. 1.4 LTS ends about Nov 2026. Pin 1.5.6 for stability or 2.0.x and accept early-adopter risk. https://duckdb.org/2026/10/21/announcing-duckdb-200 |
| Polars | 2.1.0 | 2026-10-25 | Major 2.0 shipped 2026-10-06. Requires Python >=3.11 |
| PyArrow | 26.0.0 | 2026-10-09 | Requires Python >=3.11 |
| pyiceberg | 0.12.0 | 2026-09-01 | Still 0.x |

pyiceberg local catalog: yes, `SqlCatalog` works fully offline with SQLite (`pyiceberg[sql-sqlite]`) or Postgres (`pyiceberg[sql-postgres]`), warehouse can be `file://` or an S3-compatible endpoint. Docs say not for production. Gotcha: the `sql-postgres` extra pulls `psycopg2-binary`; with psycopg3 already in the stack, install `sqlalchemy` yourself and use a `postgresql+psycopg://` URI instead of the extra. https://py.iceberg.apache.org/

---

## 3. Frontend

| Package | Version | Date | Notes |
|---|---|---|---|
| Next.js | 16.4.3 | 2026-10-23 | Major 16 since 2025-10-21. 16.4 released 2026-10-06. Node >=20.9. Frequent security releases in 2026, keep patched. https://nextjs.org/blog |
| React | 19.3.1 | 2026-10-14 | 19.3.0 on 2026-09-09 |
| TypeScript | 7.0.2 (latest tag) | 2026-07-08 | Go-native compiler. See blocker below. 6.0.3 (2026-04-16) is the last JS-based compiler |
| Tailwind CSS | 4.3.3 | 2026-07-16 | v4 is stable and default in create-next-app. CSS-first config, `@tailwindcss/postcss` 4.3.3 |
| shadcn CLI | `shadcn` 4.22.1 | 2026-10-18 | `pnpm dlx shadcn@latest init -t next` (or `--preset` from ui.shadcn.com/create). Supports `--base` primitive choice (Radix or Base UI). Tailwind v4 + React 19 supported since Feb 2025. https://ui.shadcn.com/docs/installation/next |
| Motion | `motion` 14.6.0 | 2026-10-22 | Import from `motion/react`. `framer-motion` 14.6.0 still published in lockstep. https://motion.dev |
| GSAP | `gsap` 3.15.0 | 2026-04-13 | Confirmed: 100% free incl. formerly Club plugins (SplitText, MorphSVG) for commercial use after Webflow acquisition. License is "Standard no-charge", NOT OSI open source; restriction on building no-code visual animation tools competing with Webflow. https://gsap.com/standard-license , https://webflow.com/blog/gsap-becomes-free |
| @tanstack/react-query | 5.105.0 | 2026-10-26 | v5 still current |
| Vitest | 5.0.5 | 2026-10-15 | Major 5 since 2026-09-03 |
| @playwright/test | 1.64.1 | 2026-10-14 | |
| ESLint | 10.13.0 | 2026-10-16 | ESLint 9 reached EOL 2026-08-06. Use v10 (flat config only). https://eslint.org/version-support/ |
| typescript-eslint | 8.72.1 | 2026-10-26 | Peer: eslint ^8.57 / ^9 / ^10, typescript >=4.8.4 <6.1.0 |
| eslint-config-next | 16.4.3 | | Peer eslint >=9 |
| Prettier | 3.9.10 | 2026-10-10 | |

BLOCKER: TypeScript 7.0 is incompatible with typescript-eslint today (peer range stops below 6.1.0, and TS 7's public API is not shipped until 7.1). Pin `typescript@~6.0.3` for the lint/type toolchain, or run TS 7 `tsc` for type-checking only and keep 6.0 for linting. Do not let `npm i typescript` pull 7.x by default.

Next.js static export (`output: 'export'`) constraints (official, page updated 2026-08-09):
- Dynamic routes must have `generateStaticParams()` and must NOT use `dynamicParams: true` (set `export const dynamicParams = false`).
- Unsupported: cookies, rewrites, redirects, headers, Proxy (formerly middleware), ISR, default image loader (use `images.unoptimized` or a custom loader), Draft Mode, Server Actions, intercepting routes, Route Handlers that read Request. GET Route Handlers need `export const dynamic = 'force-static'`.
- Implication: any per-entity page needs the full ID list at build time. Live data must come from client-side fetching against the Django API/WebSocket (TanStack Query), configured via `NEXT_PUBLIC_*` env vars at build time.
- https://nextjs.org/docs/app/guides/static-exports

---

## 4. CI and repo tooling

### CircleCI

- Config version: `version: 2.1` (orbs, executors, commands, parameters). https://circleci.com/docs/configuration-reference/
- Parallelism and splitting: `parallelism: N` on the job, then `circleci tests glob ... | circleci tests run --command="xargs pytest ..." --split-by=timings` (newer `tests run` form, supports rerun of failed tests) or the older `circleci tests split`. Timing data only exists if `store_test_results` uploads JUnit XML; without it the split silently falls back to name ordering. https://circleci.com/docs/guides/optimize/use-the-circleci-cli-to-split-tests/
- Secrets: Contexts (org-level env var groups, can be restricted by security group or project). https://circleci.com/docs/contexts/
- Artifacts and results: `store_artifacts` (coverage HTML, Playwright traces) and `store_test_results` (JUnit XML, drives Insights and timing splits).
- Nightly: the current mechanism is "schedule triggers" configured in Project Settings > Project setup (trigger, cron syntax, UTC, min 5 minute interval, up to 10 minute random delay). Now available for GitHub App projects too (changelog). Legacy `triggers: schedule:` workflow cron in config ("scheduled workflows") still works; its deprecation is postponed with no date. Use the schedule trigger plus a pipeline parameter or `pipeline.trigger.type` check to select the nightly workflow. Note `pipeline.trigger_source` was slated for deprecation 2026-09-21; use `pipeline.trigger.type`. UNCERTAIN: exact value names differ by VCS integration (OAuth vs GitHub App), verify in the project. https://circleci.com/changelog/schedule-triggers-now-available-for-github-app-pipelines , https://support.circleci.com/hc/en-us/articles/53583308229147
- Docker-based integration tests: Testcontainers needs a real Docker daemon reachable on localhost ports, so use the `machine` executor (`machine: image: ubuntu-2404:current` or pinned), not Docker executor plus `setup_remote_docker` (remote engine ports are not reachable from the job container). `machine: true` is deprecated on cloud. https://java.testcontainers.org/supported_docker_environment/continuous_integration/circle_ci/ , https://golang.testcontainers.org/system_requirements/ci/circle_ci

### release-please

- Runs as a standalone CLI: `npm i -g release-please` (17.11.2, 2026-08-24), commands `release-pr` and `github-release` (plus `bootstrap`). Requires `--token` (GitHub token with repo write) and `--repo-url`. It is GitHub-only (talks to GitHub REST/GraphQL), not Actions-only. https://github.com/googleapis/release-please/blob/main/docs/cli.md
- Action: `googleapis/release-please-action@v5` (v5.0.0, 2026-04-22).
- Cleanest setup with CircleCI as CI: a tiny GitHub Actions workflow on push to main running release-please-action (uses built-in `GITHUB_TOKEN`, no PAT to manage). CircleCI keeps all build/test. Alternative: a CircleCI job on main running the CLI with a fine-grained PAT stored in a Context. Caveat: releases created with the Actions `GITHUB_TOKEN` do not trigger other Actions workflows, irrelevant if CircleCI handles the rest.

### Dependabot

- `package-ecosystem: "pip"` covers pip, pip-compile (pip-tools; docs list pip-compile 7.5.3 support), pipenv, Poetry. `npm` covers npm v7 to v12 and pnpm. https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories
- pip-tools caveats (community sources): Dependabot detects `requirements.in` + compiled `requirements.txt` with the pip-compile header, re-runs pip-compile with only the options it recognizes, and may use a different pip-tools version, causing churn. Keep the `# pip-compile ...` header in compiled files, avoid exotic flags, and add a CI check that recompiles and diffs.

Example:
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule: { interval: "weekly" }
    groups: { python-minor: { update-types: ["minor", "patch"] } }
  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule: { interval: "weekly" }
    groups: { npm-minor: { update-types: ["minor", "patch"] } }
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "monthly" }
```

### Docs site: MkDocs Material vs Zensical

- Material for MkDocs entered maintenance mode on 2025-11-05 with 12 months of committed critical/security fixes (to about November 2026, i.e. now). 9.7.0 was the last feature release (all Insiders features made free). Latest 9.8.0 (2026-10-24). https://github.com/squidfunk/mkdocs-material
- MkDocs core itself: 1.6.1 (2024-08-30), repo last pushed 2025-10-20. Effectively dormant.
- Zensical (same team): 0.0.73 (2026-10-26), still 0.0.x, no 1.0 ETA. Reads `mkdocs.yml` directly. mkdocstrings support with cross-refs and objects.inv reported at parity since early 2026; blog/social plugins and a public plugin API still incomplete. https://zensical.org/compatibility , https://zensical.org/docs/setup/extensions/mkdocstrings/
- mkdocstrings: 1.0.8 (2026-10-19), active.
- Recommendation: start on Zensical with a plain `mkdocs.yml` (no blog, no social cards). If it breaks, the same config runs on MkDocs Material 9.8 unchanged. Do not invest in Material-only plugins.

---

## 5. Claude Code diagram skills

| Skill | Repo | Status | Install (from README) |
|---|---|---|---|
| diagram-design | https://github.com/cathrynlavery/diagram-design | About 61k stars, MIT, pushed 2026-10-26, created 2026-04-16. Editorial HTML + SVG, explicitly NOT Mermaid ("No Mermaid slop"), imports from Mermaid/draw.io/Excalidraw | `npx skills add cathrynlavery/diagram-design` or in Claude Code: `/plugin marketplace add cathrynlavery/diagram-design` then `/plugin install diagram-design@diagram-design`. README warns many copies exist under other names; only this repo is official |
| design-doc-mermaid | https://github.com/SpillwaveSolutions/design-doc-mermaid | About 178 stars, pushed 2026-08-24, NO LICENSE file declared (legally "all rights reserved") | `skilz install SpillwaveSolutions_design-doc-mermaid/design-doc-mermaid` or `cd ~/.claude/skills && git clone https://github.com/SpillwaveSolutions/design-doc-mermaid.git`. Needs `npm i -g @mermaid-js/mermaid-cli` for rendering |
| Most adopted Mermaid-native alternative | https://github.com/WH-2099/mermaid-skill (about 297 stars) | Smaller; not verified further | See README |

Neither is published by Anthropic; "official" here means the author's own repo. Several forks named diagram-design exist (oceanpelicanassess, mbennettGAS, bryn1, etc.); ignore them. No dedicated C4 skill with meaningful adoption found: NOT FOUND. For C4 in Mermaid, Mermaid's native `C4Context` syntax (still marked experimental by Mermaid) works with either skill.

---

## 6. AWS mapping

| Local component | AWS service(s) | Notes | Docs |
|---|---|---|---|
| Redpanda (Kafka API) | Amazon MSK (Provisioned or Serverless); Kinesis Data Streams if non-Kafka | Kafka-compatible code ports to MSK unchanged | https://docs.aws.amazon.com/msk/latest/developerguide/what-is-msk.html , https://docs.aws.amazon.com/streams/latest/dev/introduction.html |
| Redpanda Schema Registry | AWS Glue Schema Registry | Supports Avro, JSON Schema (drafts 4, 6, 7 only), Protobuf. Mismatch: Redpanda allows 2019-09/2020-12; stay on draft-07 for portability. Glue SerDes are Java-first; Python clients usually call the Glue API directly | https://docs.aws.amazon.com/glue/latest/dg/schema-registry.html |
| Postgres + pgvector | Aurora PostgreSQL (or RDS for PostgreSQL) | pgvector supported on Aurora PG | https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.AuroraPostgreSQL.html |
| SeaweedFS + Parquet | Amazon S3 data lake | | https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html |
| Object Lock (local emulation) | S3 Object Lock, compliance mode | Compliance mode: nobody incl. root can delete/shorten retention. Bucket needs versioning | https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html |
| pyiceberg SQL catalog | Amazon S3 Tables (managed Iceberg) or Glue Data Catalog Iceberg tables | S3 Tables integrate via the `s3tablescatalog` federated catalog in Glue/Lake Formation | https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables-integration-overview.html , https://docs.aws.amazon.com/lake-formation/latest/dg/create-s3-tables-catalog.html |
| DuckDB | Amazon Athena (Trino-based) | | https://docs.aws.amazon.com/athena/latest/ug/what-is.html |
| Redis (channels-redis) | Amazon ElastiCache (Valkey or Redis OSS engine) | AWS now leads with Valkey engine; channels-redis works against either | https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.html |
| Scheduled jobs | EventBridge Scheduler (cron) -> Step Functions (orchestration); MWAA for Airflow DAGs | MWAA supports Airflow 3.3.1 since 2026-09 | https://docs.aws.amazon.com/scheduler/latest/UserGuide/what-is-scheduler.html , https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html , https://docs.aws.amazon.com/mwaa/latest/userguide/what-is-mwaa.html |
| Ed25519 signing key | AWS KMS asymmetric key, key spec `ECC_NIST_EDWARDS25519`, usage SIGN_VERIFY | CONFIRMED: supported since 2025-11-07, all regions. Algorithms `ED25519_SHA_512` (requires MessageType RAW, i.e. pure Ed25519, compatible with libsodium/WebCrypto verify) and `ED25519_PH_SHA_512` (MessageType DIGEST, HashEdDSA, NOT compatible with plain Ed25519 verifiers). Use RAW. Sign payload size limit is 4096 bytes for RAW, so sign a canonical hash-chain record, not a large document | https://docs.aws.amazon.com/kms/latest/developerguide/symm-asymm-choose-key-spec.html , https://aws.amazon.com/about-aws/whats-new/2025/11/aws-kms-edwards-curve-digital-signature-algorithm/ |
| Observability (structlog, OTel) | CloudWatch Logs/Metrics, X-Ray via ADOT (AWS Distro for OpenTelemetry) | X-Ray SDKs and daemon in maintenance since 2026-02-25, end of support 2027-02-25. Instrument with OpenTelemetry/ADOT only, never the X-Ray SDK | https://docs.aws.amazon.com/xray/latest/devguide/xray-daemon-eos.html , https://aws-otel.github.io/docs/introduction |
| Hash-chained ledger table | Aurora PostgreSQL (+ pgAudit, S3 Object Lock exports) | See QLDB below | |

QLDB: end of support 2025-07-31 (already past). AWS's recommended migration target is Amazon Aurora PostgreSQL, with pgAudit, S3 and Database Activity Streams replacing journal, history and streams. This directly justifies a "hash-chained Postgres table + Object Lock exports + KMS signatures" design. https://docs.aws.amazon.com/qldb/latest/developerguide/what-is.html , https://www.infoq.com/news/2024/07/aws-kill-qldb/

UNCERTAIN: the KMS RAW 4096-byte message limit is from the Sign API reference as I recall it, not re-fetched in this session; verify at https://docs.aws.amazon.com/kms/latest/APIReference/API_Sign.html .

---

## 7. Decision-changing findings (summary)

1. Django 6.1 is not extended support; it dies December 2027, before 5.2 LTS (April 2028). Stay on 5.2 LTS; next LTS is 6.2 in April 2027.
2. MinIO community is archived and source-only. Use SeaweedFS for an Object Lock-capable local store. Garage lacks Object Lock. LocalStack now needs an auth token.
3. TypeScript `latest` is 7.0 (Go compiler) and breaks typescript-eslint (peer <6.1.0). Pin TypeScript 6.0.x.
4. ESLint 9 is EOL (2026-08-06). Use ESLint 10.
5. Major jumps since most tutorials: Next 16, Vitest 5, pytest 9, mypy 2, sentence-transformers 6, Polars 2, DuckDB 2.0 (5 days old), anthropic SDK 2.x.
6. testcontainers `RedpandaContainer` defaults to Redpanda v23.1 (no JSON Schema registry). Pin `v26.2.6`. Import from `testcontainers.community.kafka`.
7. Redpanda JSON Schema: since 24.2, but cross-subject `$ref` unsupported; Glue Schema Registry only supports drafts 4/6/7. Write schemas in draft-07 with internal refs only.
8. AWS KMS now supports Ed25519 (`ECC_NIST_EDWARDS25519`, use `ED25519_SHA_512` + RAW). Browser WebCrypto Ed25519 now works in Chrome 137+, Firefox, Safari 17+.
9. MkDocs Material maintenance window ends about now; MkDocs core dormant. Prefer Zensical with a minimal config.
10. X-Ray SDKs end support 2027-02-25: map observability to ADOT/OpenTelemetry.
11. design-doc-mermaid has no license; diagram-design (cathrynlavery) is MIT and far more adopted but is HTML/SVG, not Mermaid.
12. gitleaks is in low-maintenance mode; Betterleaks is the author's successor.
