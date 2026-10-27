# 06. Implementation Plan

> Status: Draft for MC-01. Planning style: **rolling wave**. Phases 0 to 3 are planned at task level. Phases 4 to 6 are planned at epic level and will be broken into tasks at re-planning checkpoints RP-1 and RP-2, when we know what reality taught us. Changing a later phase is expected, not a failure; every change is logged in `12-risks-and-decisions-log.md`.

## 0. Branching and pull request rules (owner decision 2026-10-27)

- **Branches are workstreams, not tasks.** One branch per major area of work (for example `docs/planning-refinements`, `feat/core-verification`, `feat/data-pipeline`, `feat/web-verifier`). A branch lives until its workstream is complete.
- **Commit continuously on the workstream branch.** Every commit is one Conventional Commit with one purpose. A correction to earlier work is its own `fix:` or `refactor:` commit, so the history shows iteration.
- **One PR per completed workstream.** Open it only when the work on that branch is finished, every test passes, CI is green, and the branch is rebased on the latest `main` with no conflicts. Then rebase-merge, so every commit lands on `main`.
- **Dependencies between workstreams use stacked branches.** If workstream B needs code from A before A is merged, B branches from A and its PR targets A. After A merges, B is rebased onto `main` with `git rebase --onto main A B`. Sibling branches are never merged into each other, because rebase-merge rewrites commit IDs and would duplicate commits on `main`.
- **Issues stay one per task** (REQ-GIT-05). A workstream PR closes all of its task issues.
- **PR size:** REQ-GIT-04's 400-line target now applies to individual commits. Workstream PRs are larger by design, so each PR description walks the reviewer through its commits in order.
- **Definition of done for a task:** tests written and passing, docs touched where behavior changed, conventions documented where they changed. A review pass with comments happens on every workstream PR (REQ-GIT-06).
- TDD for `core`, `ledger`, `ingestion`, `reconciliation`, the analyst query compiler and verifier, and the data quality checks.
- Schema changes are their own commits, never mixed with feature code (brief Section 14).


### Workstream branches

| Branch | Holds | Depends on |
|---|---|---|
| `docs/documentation` | Every documentation change: planning docs, ADRs, README, runbook, data profiles | none |
| `build/foundation` | Python project, venv and pip-tools, quality tooling, Makefile, CircleCI, issue bootstrap script | none |
| `feat/core-verification` | Canonical JSON, IDs, money, Merkle log, consistency proofs, checkpoints, Bloom filter, replay exporter | `build/foundation` |
| `feat/data-pipeline` | Real-data acquisition, Spark bronze/silver/gold, PII removal, Deequ checks, anomaly overlay, Kafka replay, live connector | `build/foundation`; replay exporter needs `feat/core-verification` |
| `feat/web-app` | Next.js app: verifier library, pages, static deploy, later all UI epics | test vectors from `feat/core-verification` |
| `feat/streaming-ledger` | Django backend, compose stack, ingestion, ledger, checkpointer, API, reconciliation, realtime | `feat/core-verification`, `feat/data-pipeline` |
| `feat/ai-analyst` | Query IR, retrieval, composer, verifier, evals | `feat/streaming-ledger` |

Later phases add branches at the same level (for example `feat/lake-and-scale`). Dependencies are handled as stacked branches (section above).

Day numbering: Day 1 = Tuesday 2026-10-27. Days are targets, not promises. "Exit" is what must be true to close the issue.

Milestones: **MVP** (`v0.1.0`), **MLP**, **Nice-to-have** (`v1.0.0`). Phase 0 and 1 tasks belong to MVP.

---

## Phase 0: Planning and repository bootstrap (Day 0 to Day 1)

Goal: approved plan, protected repo, issues on a board.

| ID | Workstream branch | Issue title | REQs | Status / exit |
|---|---|---|---|---|
| T-001 | (initial commit) | `chore: initialize repository` | GIT-09 (partial) | Done. The only direct push to `main` |
| MC-03 | n/a | Branch protection on `main` | GIT-03 | Done. PR required, linear history, no force push, admins included, no required approvals. Status checks added at T-103 |
| T-002a..g | `docs/t002*` (merged, then consolidated into `docs/documentation`) | Planning docs in seven batches | DOC-05, DOC-07, all planning docs | Done (PRs #4 to #16) |
| T-003 | `chore/t003-repo-governance` (merged, deleted) | `chore: add governance files and GitHub templates` | GIT-04, GIT-09 | Done (PR #2) |
| T-005 | `docs/t005-design-review-revisions` (merged, consolidated) | `docs: apply design review findings to planning docs` | all | Done (PR #18) |
| T-007 | `docs/documentation` | Rename to Tallyproof, workstream branching, real-data architecture, CLI-only setup | SEC-09 (amended) | In progress |
| T-004 | `build/foundation` | `chore: add script to create milestones, labels, and issues from the plan` | GIT-05 | Script parses this file and creates issues idempotently via `gh` |

## Phase 1a: Static proof slice (Day 1 to Day 3)

Goal: a public page anyone can open with no install: a real event, a real proof from the real `core` library, Verify in the browser, edit a field, watch Verify fail. **No Kafka, no Postgres yet.** This is what outside reviewers see first, so it ships before the infrastructure.

| ID | Workstream branch | Issue title | REQs | Exit |
|---|---|---|---|---|
| T-101 | `build/foundation` | `build(backend): scaffold Python project with venv and pip-tools` | ENV-01, ENV-02 | `backend/` with `pyproject.toml`, `requirements*.in/.txt` (hashes), `tallyproof_core` package skeleton |
| T-102 | `build/foundation` | `build: add ruff, mypy strict, pytest, pre-commit, and Makefile` | QA-01..03, GIT-07, SEC-04, CI-04 | `make lint typecheck test` pass; pre-commit runs ruff, ruff-format, mypy, gitleaks (custom rule for key files), conventional-pre-commit; Makefile refuses to run outside `.venv` |
| T-103 | `build/foundation` | `ci: add CircleCI pipeline with a single required gate` | CI-01 (partial), CI-03, CI-04, SEC-04, SEC-05, GIT-01 | Jobs: lint, typecheck, unit (parallelism 1 until the suite exceeds 2 minutes), commit-message lint over every commit in the PR, gitleaks, literal check for hardcoded URLs and model IDs; one always-running `ci-gate` job is the only required status check. **MC-04** here (confirm plan credits and that forked-PR secrets are off) |
| T-105 | `feat/core-verification` | `feat(core): add canonical JSON, seeded prefixed IDs, and money type` | URL-02, QA-04 | RFC 8785 via `rfc8785`; `new_id(prefix, clock, rng)`; Decimal money; vectors at repo-root `testdata/vectors/` |
| T-106 | `feat/core-verification` | `feat(core): add RFC 9162 Merkle log with inclusion proofs` | QA-04, QA-08 | Reference vectors vendored from transparency-dev/merkle with license attribution (RFC 9162 itself has no vector appendix); Hypothesis properties; module coverage >= 95%; exports `merkle.json` vectors |
| T-107 | `feat/core-verification` | `feat(core): add Merkle consistency proofs` | QA-04 | Properties for all m <= n; exports vectors |
| T-109 | `feat/core-verification` | `feat(core): add C2SP signed checkpoints` | SEC-01 | Exact signed-note bytes documented (key hash, U+2014 signature line); strict RFC 8032 verification; exports `checkpoint.json` vectors; keys generated at runtime in tests |
| T-110 | `feat/data-pipeline` | `feat(events): add event envelope and leaf document schemas` | SEC-08 (validation) | `LeafDocument` field list; integer and Unicode rules; JSON Schema draft-07 export |
| T-111 | `feat/data-pipeline` | `feat(data): add labeled anomaly overlay on real events` | DRV-HYG-02, EVAL-01 | Seeded injection of `duplicate_delivery`, `amount_mismatch`, `orphan_outlay`, `injection_memo` into conformed real events; labels only in `manifest.jsonl`; same seed gives byte-identical output |
| D-02 | `feat/data-pipeline` | `feat(data): add archive downloader with source manifest` | ADR-0016 | Resumable, rate-limited download from official endpoints; manifest records URL, size, SHA-256, fetch time; file hashes become ledger leaves later |
| D-03 | `feat/data-pipeline` | `feat(data): add Spark bronze-to-silver job with PII removal and quarantine` | SEC-09, ADR-0017 | One CSV member at a time; typed Parquet; PII columns and individual-recipient rows dropped with counts logged; quarantine with reason codes; test proves no PII column survives |
| D-04 | `feat/data-pipeline` | `feat(data): add Deequ data quality constraints and metrics history` | ADR-0017 | Completeness, uniqueness, range, and referential constraints; build fails on error-level checks |
| D-05 | `feat/data-pipeline` | `feat(data): add committed CI sample of real rows` | QA-06 | About 50k PII-free rows with the full schema, used by CI and the static demo |
| D-06 | `feat/data-pipeline` | `feat(data): conform silver rows into ledger events` | ADR-0016 | Gold events in event-time order, validated against the `LeafDocument` rules |
| T-121 | `feat/core-verification` | `feat(core): add deterministic replay bundle exporter` | OPS-02 | Builds the log from a seeded scenario in deterministic order, signs with the published demo key, writes `replay/` with a signed manifest; same seed and commit give the same root |
| T-117 | `feat/web-app` | `build(web): scaffold Next.js app with themes and quality tooling` | QA-10, UI-06, ENV-03, CI-02 | Spike first: ESLint 10 with every plugin in `eslint-config-next` (fallback pre-approved: `typescript-eslint` plus `@next/eslint-plugin-next` only). Spike second: one route file serving both static export and live mode; decision recorded (Q-06). Light and dark tokens; web jobs feed `ci-gate` |
| T-118 | `feat/web-app` | `feat(web): add browser verification library mirrored from core` | URL-04, OPS-02 | `canonicalize`, `@noble/hashes`, `@noble/ed25519` in strict mode (`zip215: false`); passes every shared vector including generator `injection_memo` cases |
| T-119 | `feat/web-app` | `feat(web): add event page with Verify and tamper toggle` | UI-03 (component), UI-04 (partial), UI-06 | Reads the replay bundle; untampered event re-canonicalized in the browser equals the bundle bytes; tamper levels 1 and 2 fail with the right reason; pinned key fingerprint shown; keyboard accessible; both themes |
| T-122 | `feat/web-app` | `ci(web): build and publish the static replay site` | OPS-02 | Static export published (Vercel after **MC-06**, pulled forward; GitHub Pages as a no-account fallback) |
| T-120 | `docs/documentation` | `docs(readme): link the live proof page and update status` | DOC-01 (partial) | README status banner says exactly what works; links the hosted page |

## Phase 1b: Live pipeline (Day 4 to Day 6)

Goal: the same proofs, now produced by a real streaming pipeline: `make demo` brings everything up.

| ID | Workstream branch | Issue title | REQs | Exit |
|---|---|---|---|---|
| T-126 | `feat/streaming-ledger` | `build(backend): add Django 5.2 project with typed settings` | SEC-01..03, SEC-06 | `config/settings/{base,local,test,ci}.py`; `config/env.py` fails fast; per-process settings subclasses; `.env.example` documented; `django-cors-headers` |
| T-104 | `feat/streaming-ledger` | `build(infra): add compose stack, database roles, and health checks` | OPS-01 (partial), URL-05, SEC-07 | Redpanda + Console, Postgres + pgvector, Redis bound to 127.0.0.1; `make db-roles` script; `/healthz`, `/readyz` |
| T-108 | `feat/core-verification` | `feat(core): add Bloom filter with sizing math` | QA-04 | No-false-negative property; FPR within bound; snapshot serialization |
| T-112 | `feat/streaming-ledger` | `feat(ledger): add append-only ledger schema` | DRV-HYG-03 | `ledger_event` (generated `payload`), `ledger_batch`, `merkle_log_head`, `consumer_offset`, `dedupe_rejection`, `outbox`; triggers |
| T-112b | `feat/streaming-ledger` | `feat(ledger): add role grants migration` | SEC-07 | Idempotent RunSQL with default privileges; TRUNCATE revoked; grant tests via `SET ROLE` |
| T-113a | `feat/streaming-ledger` | `feat(ledger): add append service with contiguous leaf allocation` | QA-05 | Property: random rollbacks never leave a gap |
| T-113b | `feat/streaming-ledger` | `feat(ingestion): add consumer loop with fenced offsets in Postgres` | QA-05 | Seek on assign; GREATEST plus generation fence; restart test: no duplicates, no gaps |
| T-113c | `feat/streaming-ledger` | `feat(ingestion): add Bloom dedupe with rebuild on assignment` | QA-05 | Staged insert; intra-batch duplicates caught; rebuild in `on_assign` |
| T-113d | `feat/streaming-ledger` | `feat(ingestion): route invalid events to the dead-letter topic` | SEC-08 | Error envelope; offset advances |
| T-114 | `feat/streaming-ledger` | `feat(ledger): add checkpointer, witness export, and external timestamps` | ADR-0003, ADR-0007 | Size-or-time batches; signed checkpoints; `var/witness/`; OpenTimestamps proofs |
| T-115a | `feat/streaming-ledger` | `feat(api): add event, proof, checkpoint, and log-key endpoints` | URL-01..04 | RFC 9457 errors; proofs, never verdicts |
| T-115b | `feat/streaming-ledger` | `feat(api): add list endpoints, throttling, and OpenAPI docs` | URL-01, SEC-10 | Cursor pagination caps; trusted proxy config |
| T-116 | `feat/streaming-ledger` | `test: add Testcontainers integration test from generator to proof` | QA-06, QA-07 (partial) | Redpanda image pinned to v26.2.6 |
| T-116b | `feat/streaming-ledger` | `ci: run integration tests on the machine executor` | CI-01, QA-06 | Runs on `main` and on PRs touching ingestion, ledger, or infra; reports into `ci-gate` |
| D-07 | `feat/data-pipeline` | `feat(data): run full FY2025 build and commit the profiling report` | DRV-HYG-05 | About 13 GB of CSV processed within the resource budget; `docs/data/profile-fy2025.md` committed with row counts, null rates, distributions, and dropped-row counts |
| D-08 | `feat/data-pipeline` | `feat(data): add Kafka replay producer for gold events` | OPS-01 | Event-time order, configurable rate and slice size, keyed by account; replaces the old synthetic producer task |
| D-09 | `feat/data-pipeline` | `feat(data): add Treasury Daily Treasury Statement live connector` | ADR-0016 | Fetches each business day's deposits and withdrawals into Kafka; idempotent by record date |
| T-123 | `feat/streaming-ledger` | `build(infra): add compose services for API, workers, and web` | OPS-01 | `make demo` is the one command: stack, migrations, roles, seed, workers, web |
| T-124 | `feat/web-app` | `feat(web): add live data mode to the event page` | UI-03 (component) | Same page, live API |
| T-120b | `docs/documentation` | `docs(readme): add quickstart for the live pipeline` | DOC-01 (partial), DOC-02 | Three-command quickstart verified on a clean clone; app READMEs |

**RP-1 (end of Day 6): re-plan.** Compare velocity with this plan, update Phases 2 to 6, log changes. First `/graphify` run on the codebase.

## Phase 2: Pipeline depth (Day 7 to Day 11)

Goal: the pipeline looks like something a data-platform team would run: full anomaly catalog, outbox, reconciliation, double-entry, consistency verification, tamper ladder, observability, control totals.

| ID | Workstream branch | Issue title | REQs | Exit |
|---|---|---|---|---|
| T-201 | `feat/data-pipeline` | `feat(generator): complete anomaly catalog and scenario sizes` | EVAL-01 (data) | All labels in `05-backend-structure.md` section 5; sizes smoke, demo, full, volume |
| T-202 | `feat/streaming-ledger` | `feat(ledger): add transactional outbox relay to ledger.appended` | n/a | LISTEN/NOTIFY wake-up (no busy polling); idempotent by outbox ID; lag metric |
| T-203 | `feat/streaming-ledger` | `feat(ledger): add journal and reconciliation schema migrations` | HYG migration | `journal_line`, `recon_break`, `break_event`; balanced-entry deferred trigger |
| T-204 | `feat/streaming-ledger` | `feat(ledger): derive double-entry journal from events` | QA-04 | Property: every entry balances; trial balance equals zero; deterministic re-derivation |
| T-205 | `feat/streaming-ledger` | `feat(reconciliation): add matching rules and break types` | QA-04, QA-08 | Pure rule engine; unit tests per anomaly type; split and partial payments; tolerance from config |
| T-206 | `feat/streaming-ledger` | `feat(reconciliation): add worker, breaks topic, and breaks API` | URL-01 | `recon.breaks.v1`; `/api/v1/reconciliation/breaks`; anomaly recall = 1.0 on catalog against manifest |
| T-207 | `feat/streaming-ledger` | `feat(api): add consistency proofs and witness verification` | URL-04 | `/batches/{id}/consistency`; `make verify-witness` checks every committed checkpoint is consistent with the live log |
| T-208 | `feat/streaming-ledger` | `feat(ledger): add guarded tamper tool for ladder levels 1 to 4` | UI-04 (backend) | `make tamper LEVEL=n` (only when `DEMO_TAMPER_ENABLED`); tests assert each level is caught by the expected mechanism |
| T-209 | `feat/streaming-ledger` | `feat(realtime): add WebSocket stream of ledger facts` | UI-02 (backend) | Channels + Redis; `/ws/v1/stream`; backpressure: drop-to-latest for slow clients |
| T-210 | `feat/streaming-ledger` | `feat: add structlog JSON logging with end-to-end correlation IDs` | HYG correlation | One `correlation_id` traceable from generator to ledger to answer |
| T-211 | `feat/streaming-ledger` | `feat(ingestion): add DLQ inspection and replay command` | n/a | Replays fixed messages; idempotent |
| T-212 | `feat/streaming-ledger` | `feat: add control totals across topic and ledger` | n/a | Per batch count and sum match between Kafka offsets range and ledger; mismatch fails `make check-totals` |
| D-10 | `feat/data-pipeline` | `feat(data): add FY2024 and account-level outlay data` | ADR-0016 | Total about 27 GB of contract CSV processed; outlays joined for reconciliation (scope depends on research note R-01) |
| D-11 | `feat/data-pipeline` | `feat(data): add Federal Acquisition Regulation policy corpus` | SEC-08 | Public-domain policy text versioned as document leaves for Phase 3 retrieval |
| T-215 | `feat/streaming-ledger` | `feat(events): register schemas with BACKWARD compatibility` | n/a | Redpanda Schema Registry; incompatible change fails CI |
| T-216 | `feat/streaming-ledger` | `feat: add commands to rebuild derived state from the ledger` | n/a | Journal, breaks, and lake rebuildable from Postgres after a rule change; runbook entry |
| T-214 | `docs/documentation` | `docs: refresh architecture, ADRs, and diagrams after phase 2` | DOC-03, DOC-04, DOC-05 | Diagrams regenerated with the MC-08 skill if installed |

## Phase 3: Analyst and evals (Day 11 to Day 17)

Goal: ask a question, get bound numbers and verifiable citations or a justified refusal; evals gate CI.

| ID | Workstream branch | Issue title | REQs | Exit |
|---|---|---|---|---|
| T-301 | `feat/ai-analyst` | `feat(analyst): add curated analyst views and read-only role` | SEC-07 | Views in `analyst` schema; integration test: role cannot write even with guard bypassed |
| T-300 | `feat/ai-analyst` | `test(evals): add frozen held-out question set` | EVAL-01 | 40 free-form questions written before any prompt work; 10 hand-verified answers |
| T-302 | `feat/ai-analyst` | `feat(analyst): add constrained query IR and SQL compiler` | SEC-07, QA-04 | ADR-0014 shapes; provenance per shape; filter rendered in words |
| T-302b | `feat/ai-analyst` | `feat(analyst): add hardened SQL guard for the fallback path` | SEC-07 | Threat model 5.3 corpus rejected; generic error codes only |
| T-303 | `feat/ai-analyst` | `feat(analyst): add LLM client interface, fake client, cache, and budgets` | QA-09, EVAL-05, SEC-01 | No module test touches network; model IDs from settings |
| T-304 | `feat/ai-analyst` | `feat(analyst): add rules-first question router` | n/a | Router accuracy measured on golden categories |
| T-305 | `feat/ai-analyst` | `feat(analyst): add policy corpus, document leaves, and vector retrieval` | SEC-08 | Policy docs hashed into the log as leaves; chunks embedded locally; hybrid retrieval |
| T-306 | `feat/ai-analyst` | `feat(analyst): add slot-bound composer, verifier, and refusal policy` | SEC-08 | Free-number violations rejected; citations limited to evidence set; quote substring check |
| T-307 | `feat/ai-analyst` | `feat(api): add queries and answers endpoints with rate limits` | URL-01..03, SEC-10 | `POST /api/v1/queries`, `GET /api/v1/answers/{id}` |
| T-308 | `feat/ai-analyst` | `feat(evals): add independent oracle and golden set builder` | EVAL-01 | Oracle shares no code with analyst; smoke set of 20 fixed |
| T-309 | `feat/ai-analyst` | `feat(evals): add runner, metrics, thresholds, and reports` | EVAL-02, EVAL-05 | JSON + Markdown report; `eval_run` rows |
| T-310 | `feat/ai-analyst` | `ci: add smoke eval gate and nightly full eval` | EVAL-03, EVAL-04, CI-01, CI-03 | Gate fails below thresholds; nightly scheduled pipeline |
| MC-05 | n/a | Anthropic API key with budget | n/a | Only now does a real LLM get called |
| T-311 | `feat/ai-analyst` | `feat(analyst): add Claude client and record first live baseline` | EVAL-04 | Thresholds set from baseline; decision logged |
| T-312 | `feat/web-app` | `feat(web): add analyst page with cited answers and Verify` | UI-03 | Each citation expands to event and proof path; Verify per citation; refused answers explained |
| T-313 | `feat/ai-analyst` | `test: add end-to-end test from generator to verified answer` | QA-07 | Pytest e2e using recorded LLM responses |

**RP-2 (end of Day 17): re-plan Phases 4 to 6** with real numbers from evals and load.

## Phase 4: MVP close (Day 17 to Day 19), epic level

| ID | Epic | REQs |
|---|---|---|
| E-401 | Coverage gate >= 85% on core modules enforced in CI | QA-08 |
| E-402 | release-please wired (CHANGELOG from commits); tag `v0.1.0` | GIT-08 |
| E-403 | MkDocs site with mkdocstrings published to GitHub Pages | DOC-06 |
| E-404 | Threat model review against the built system; security review pass with compound-engineering security reviewers | SEC-11 |
| E-405 | Docs refresh: architecture, runbook, configuration, contributor guide | DOC-03, DOC-07 |
| E-406 | Module test audit: every Django app has module tests with faked dependencies | QA-05 |

Rule from the brief: if MVP is not green by end of Week 3, MLP pauses.

## Phase 5: MLP experience and data depth (Day 19 to Day 26), epic level

| ID | Epic | REQs |
|---|---|---|
| E-501 | Motion landing page: event flows through stream, hashed into tree, appears as verified citation | UI-01 |
| E-502 | Live stream dashboard | UI-02 |
| E-503 | Citation proof visualization: animated audit path with Verify | UI-03 |
| E-504 | Tamper ladder demo, levels 1 to 4, in browser | UI-04 |
| E-505 | Eval dashboard across runs, including naive baseline column | UI-05, EVAL-06 |
| E-506 | Replay bundle export and static build; Vercel project (**MC-06**); README states which mode the link runs | OPS-02 |
| E-507 | Playwright flows: landing, verify, tamper, analyst, evals | QA-07 |
| E-508 | Iceberg tables (pyiceberg) on S3-compatible store with Bloom dedupe in the sink; control totals extended to lake | (data signal) |
| E-509 | Measured load-test report: throughput, lag, p50/p95/p99, hardware stated | HYG-05 |
| E-510 | README hero diagram (MC-08 skill), tamper GIF, nightly eval table refresh via bot PR | DOC-01, EVAL-06 |
| E-511 | Accessibility pass: keyboard paths, contrast, reduced motion | UI-06 |

## Phase 6: Nice-to-have and v1.0.0 (Day 26 to Day 31), epic level

| ID | Epic |
|---|---|
| E-601 | Count-Min Sketch heavy hitters for `vendor_burst` |
| E-602 | Schema evolution demo v1 to v2 (registry itself lands in T-215) |
| E-603 | DuckDB batch reconciliation over 10M+ rows in the lake; streaming versus batch comparison |
| E-604 | Merkle-sum tree for provable totals |
| E-605 | OpenTelemetry tracing |
| E-606 | AWS reference architecture IaC sketch (not deployed) |
| E-607 | Optional live backend (**MC-07**), never load-bearing (OPS-03) |
| E-608 | Tag `v1.0.0` |

## Re-planning checkpoints

| ID | When | Inputs | Output |
|---|---|---|---|
| RP-1 | End of Phase 1b (Day 6) | Actual velocity, CI time, any design surprises | Updated Phases 2 to 6, decisions logged |
| RP-2 | End of Phase 3 | First live eval numbers, latency, cost | Phases 4 to 6 broken into tasks; thresholds set |
| RP-3 | End of Phase 5 | Remaining days | Pick which Nice-to-haves to do |
