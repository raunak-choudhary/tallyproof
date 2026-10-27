# 06. Implementation Plan

> Status: Draft for MC-01. Planning style: **rolling wave**. Phases 0 to 3 are planned at task level. Phases 4 to 6 are planned at epic level and will be broken into tasks at re-planning checkpoints RP-1 and RP-2, when we know what reality taught us. Changing a later phase is expected, not a failure; every change is logged in `12-risks-and-decisions-log.md`.

## 0. Rules for every task

- One task = one GitHub issue = one branch = one PR (REQ-GIT-02, REQ-GIT-05).
- Branch: `<type>/<task-id>-<slug>`, for example `feat/t106-merkle-log`.
- PR title and every commit are Conventional Commits. PRs are rebase-merged so each commit is visible on `main` (owner decision 2026-10-27, refines REQ-GIT-03's squash rule).
- Target under about 400 changed lines excluding lockfiles and generated files (REQ-GIT-04). If a task grows, split it and record the split.
- Definition of done: CI green, review pass with comments left on the PR (REQ-GIT-06), docs touched where behavior changed, CLAUDE.md updated if a convention changed, issue closed by the PR.
- Merged branches are kept (not deleted) until Raunak decides to bulk-clean them.
- TDD for `core`, `ledger`, `ingestion`, `reconciliation`, `analyst/sql_guard`, `analyst/verifier`: tests first.
- Schema changes are their own PR (brief Section 14).

Day numbering: Day 1 = Tuesday 2026-10-27. Days are targets, not promises. "Exit" is what must be true to close the issue.

Milestones: **MVP** (`v0.1.0`), **MLP**, **Nice-to-have** (`v1.0.0`). Phase 0 and 1 tasks belong to MVP.

---

## Phase 0: Planning and repository bootstrap (Day 0 to Day 1)

Goal: approved plan, protected repo, issues on a board.

| ID | Branch | PR / issue title | REQs | Status / exit |
|---|---|---|---|---|
| T-001 | (initial commit) | `chore: initialize repository` | GIT-09 (partial) | Done. The only direct push to `main` |
| MC-03 | n/a | Branch protection on `main` | GIT-03 | Done. PR required, linear history, no force push, admins included, no required approvals. Status checks added at T-103 |
| T-002a..g | `docs/t002*-*` | Planning docs in seven batches | DOC-05, DOC-07, all planning docs | Done (PRs #4 to #16) |
| T-003 | `chore/t003-repo-governance` | `chore: add governance files and GitHub templates` | GIT-04, GIT-09 | Done (PR #2) |
| T-005 | `docs/t005-design-review-revisions` | `docs: apply design review findings to planning docs` | all | This revision |
| T-004 | `chore/t004-issue-bootstrap` | `chore: add script to create milestones, labels, and issues from the plan` | GIT-05 | Script parses this file and creates issues idempotently via `gh` |

## Phase 1a: Static proof slice (Day 1 to Day 3)

Goal: a public page anyone can open with no install: a real event, a real proof from the real `core` library, Verify in the browser, edit a field, watch Verify fail. **No Kafka, no Postgres yet.** This is what outside reviewers see first, so it ships before the infrastructure.

| ID | Branch | PR / issue title | REQs | Exit |
|---|---|---|---|---|
| T-101 | `build/t101-python-project` | `build(backend): scaffold Python project with venv and pip-tools` | ENV-01, ENV-02 | `backend/` with `pyproject.toml`, `requirements*.in/.txt` (hashes), `tallyproof_core` package skeleton |
| T-102 | `build/t102-quality-tooling` | `build: add ruff, mypy strict, pytest, pre-commit, and Makefile` | QA-01..03, GIT-07, SEC-04, CI-04 | `make lint typecheck test` pass; pre-commit runs ruff, ruff-format, mypy, gitleaks (custom rule for key files), conventional-pre-commit; Makefile refuses to run outside `.venv` |
| T-103 | `ci/t103-circleci-pipeline` | `ci: add CircleCI pipeline with a single required gate` | CI-01 (partial), CI-03, CI-04, SEC-04, SEC-05, GIT-01 | Jobs: lint, typecheck, unit (parallelism 1 until the suite exceeds 2 minutes), commit-message lint over every commit in the PR, gitleaks, literal check for hardcoded URLs and model IDs; one always-running `ci-gate` job is the only required status check. **MC-04** here (confirm plan credits and that forked-PR secrets are off) |
| T-105 | `feat/t105-canonical-ids-money` | `feat(core): add canonical JSON, seeded prefixed IDs, and money type` | URL-02, QA-04 | RFC 8785 via `rfc8785`; `new_id(prefix, clock, rng)`; Decimal money; vectors at repo-root `testdata/vectors/` |
| T-106 | `feat/t106-merkle-log` | `feat(core): add RFC 9162 Merkle log with inclusion proofs` | QA-04, QA-08 | Reference vectors vendored from transparency-dev/merkle with license attribution (RFC 9162 itself has no vector appendix); Hypothesis properties; module coverage >= 95%; exports `merkle.json` vectors |
| T-107 | `feat/t107-consistency-proofs` | `feat(core): add Merkle consistency proofs` | QA-04 | Properties for all m <= n; exports vectors |
| T-109 | `feat/t109-signed-checkpoints` | `feat(core): add C2SP signed checkpoints` | SEC-01 | Exact signed-note bytes documented (key hash, U+2014 signature line); strict RFC 8032 verification; exports `checkpoint.json` vectors; keys generated at runtime in tests |
| T-110 | `feat/t110-event-schemas` | `feat(events): add event envelope and leaf document schemas` | SEC-08 (validation) | `LeafDocument` field list; integer and Unicode rules; JSON Schema draft-07 export |
| T-111 | `feat/t111-generator-v1` | `feat(generator): add seeded scenario generator with first anomalies` | DRV-HYG-02, SEC-09 | Byte-identical output per seed; anomalies `duplicate_delivery`, `orphan_payment`, `amount_mismatch`, `injection_memo`; separate `manifest.jsonl`; `make seed` writes JSONL (Kafka producer added in T-125) |
| T-121 | `feat/t121-replay-exporter` | `feat(core): add deterministic replay bundle exporter` | OPS-02 | Builds the log from a seeded scenario in deterministic order, signs with the published demo key, writes `replay/` with a signed manifest; same seed and commit give the same root |
| T-117 | `build/t117-frontend-skeleton` | `build(web): scaffold Next.js app with themes and quality tooling` | QA-10, UI-06, ENV-03, CI-02 | Spike first: ESLint 10 with every plugin in `eslint-config-next` (fallback pre-approved: `typescript-eslint` plus `@next/eslint-plugin-next` only). Spike second: one route file serving both static export and live mode; decision recorded (Q-06). Light and dark tokens; web jobs feed `ci-gate` |
| T-118 | `feat/t118-web-verifier` | `feat(web): add browser verification library mirrored from core` | URL-04, OPS-02 | `canonicalize`, `@noble/hashes`, `@noble/ed25519` in strict mode (`zip215: false`); passes every shared vector including generator `injection_memo` cases |
| T-119 | `feat/t119-event-verify-page` | `feat(web): add event page with Verify and tamper toggle` | UI-03 (component), UI-04 (partial), UI-06 | Reads the replay bundle; untampered event re-canonicalized in the browser equals the bundle bytes; tamper levels 1 and 2 fail with the right reason; pinned key fingerprint shown; keyboard accessible; both themes |
| T-122 | `ci/t122-static-deploy` | `ci(web): build and publish the static replay site` | OPS-02 | Static export published (Vercel after **MC-06**, pulled forward; GitHub Pages as a no-account fallback) |
| T-120 | `docs/t120-readme-v1` | `docs(readme): link the live proof page and update status` | DOC-01 (partial) | README status banner says exactly what works; links the hosted page |

## Phase 1b: Live pipeline (Day 4 to Day 6)

Goal: the same proofs, now produced by a real streaming pipeline: `make demo` brings everything up.

| ID | Branch | PR / issue title | REQs | Exit |
|---|---|---|---|---|
| T-126 | `build/t126-django-project` | `build(backend): add Django 5.2 project with typed settings` | SEC-01..03, SEC-06 | `config/settings/{base,local,test,ci}.py`; `config/env.py` fails fast; per-process settings subclasses; `.env.example` documented; `django-cors-headers` |
| T-104 | `build/t104-local-stack` | `build(infra): add compose stack, database roles, and health checks` | OPS-01 (partial), URL-05, SEC-07 | Redpanda + Console, Postgres + pgvector, Redis bound to 127.0.0.1; `make db-roles` script; `/healthz`, `/readyz` |
| T-108 | `feat/t108-bloom-filter` | `feat(core): add Bloom filter with sizing math` | QA-04 | No-false-negative property; FPR within bound; snapshot serialization |
| T-112 | `feat/t112-ledger-schema` | `feat(ledger): add append-only ledger schema` | DRV-HYG-03 | `ledger_event` (generated `payload`), `ledger_batch`, `merkle_log_head`, `consumer_offset`, `dedupe_rejection`, `outbox`; triggers |
| T-112b | `feat/t112b-ledger-grants` | `feat(ledger): add role grants migration` | SEC-07 | Idempotent RunSQL with default privileges; TRUNCATE revoked; grant tests via `SET ROLE` |
| T-113a | `feat/t113a-append-service` | `feat(ledger): add append service with contiguous leaf allocation` | QA-05 | Property: random rollbacks never leave a gap |
| T-113b | `feat/t113b-consumer-offsets` | `feat(ingestion): add consumer loop with fenced offsets in Postgres` | QA-05 | Seek on assign; GREATEST plus generation fence; restart test: no duplicates, no gaps |
| T-113c | `feat/t113c-bloom-dedupe` | `feat(ingestion): add Bloom dedupe with rebuild on assignment` | QA-05 | Staged insert; intra-batch duplicates caught; rebuild in `on_assign` |
| T-113d | `feat/t113d-dlq` | `feat(ingestion): route invalid events to the dead-letter topic` | SEC-08 | Error envelope; offset advances |
| T-125 | `feat/t125-generator-producer` | `feat(generator): produce scenarios to Redpanda` | OPS-01 | Keyed by `account_id` |
| T-114 | `feat/t114-checkpointer` | `feat(ledger): add checkpointer, witness export, and external timestamps` | ADR-0003, ADR-0007 | Size-or-time batches; signed checkpoints; `var/witness/`; OpenTimestamps proofs |
| T-115a | `feat/t115a-proof-api` | `feat(api): add event, proof, checkpoint, and log-key endpoints` | URL-01..04 | RFC 9457 errors; proofs, never verdicts |
| T-115b | `feat/t115b-list-api` | `feat(api): add list endpoints, throttling, and OpenAPI docs` | URL-01, SEC-10 | Cursor pagination caps; trusted proxy config |
| T-116 | `test/t116-integration-slice` | `test: add Testcontainers integration test from generator to proof` | QA-06, QA-07 (partial) | Redpanda image pinned to v26.2.6 |
| T-116b | `ci/t116b-integration-job` | `ci: run integration tests on the machine executor` | CI-01, QA-06 | Runs on `main` and on PRs touching ingestion, ledger, or infra; reports into `ci-gate` |
| T-123 | `build/t123-app-services` | `build(infra): add compose services for API, workers, and web` | OPS-01 | `make demo` is the one command: stack, migrations, roles, seed, workers, web |
| T-124 | `feat/t124-live-event-page` | `feat(web): add live data mode to the event page` | UI-03 (component) | Same page, live API |
| T-120b | `docs/t120b-readme-v2` | `docs(readme): add quickstart for the live pipeline` | DOC-01 (partial), DOC-02 | Three-command quickstart verified on a clean clone; app READMEs |

**RP-1 (end of Day 6): re-plan.** Compare velocity with this plan, update Phases 2 to 6, log changes. First `/graphify` run on the codebase.

## Phase 2: Pipeline depth (Day 7 to Day 11)

Goal: the pipeline looks like something a data-platform team would run: full anomaly catalog, outbox, reconciliation, double-entry, consistency verification, tamper ladder, observability, control totals.

| ID | Branch | PR / issue title | REQs | Exit |
|---|---|---|---|---|
| T-201 | `feat/t201-generator-catalog` | `feat(generator): complete anomaly catalog and scenario sizes` | EVAL-01 (data) | All labels in `05-backend-structure.md` section 5; sizes smoke, demo, full, volume |
| T-202 | `feat/t202-outbox-relay` | `feat(ledger): add transactional outbox relay to ledger.appended` | n/a | LISTEN/NOTIFY wake-up (no busy polling); idempotent by outbox ID; lag metric |
| T-203 | `feat/t203-journal-recon-schema` | `feat(ledger): add journal and reconciliation schema migrations` | HYG migration | `journal_line`, `recon_break`, `break_event`; balanced-entry deferred trigger |
| T-204 | `feat/t204-double-entry` | `feat(ledger): derive double-entry journal from events` | QA-04 | Property: every entry balances; trial balance equals zero; deterministic re-derivation |
| T-205 | `feat/t205-recon-rules` | `feat(reconciliation): add matching rules and break types` | QA-04, QA-08 | Pure rule engine; unit tests per anomaly type; split and partial payments; tolerance from config |
| T-206 | `feat/t206-recon-worker` | `feat(reconciliation): add worker, breaks topic, and breaks API` | URL-01 | `recon.breaks.v1`; `/api/v1/reconciliation/breaks`; anomaly recall = 1.0 on catalog against manifest |
| T-207 | `feat/t207-consistency-api` | `feat(api): add consistency proofs and witness verification` | URL-04 | `/batches/{id}/consistency`; `make verify-witness` checks every committed checkpoint is consistent with the live log |
| T-208 | `feat/t208-tamper-ladder` | `feat(ledger): add guarded tamper tool for ladder levels 1 to 4` | UI-04 (backend) | `make tamper LEVEL=n` (only when `DEMO_TAMPER_ENABLED`); tests assert each level is caught by the expected mechanism |
| T-209 | `feat/t209-realtime-stream` | `feat(realtime): add WebSocket stream of ledger facts` | UI-02 (backend) | Channels + Redis; `/ws/v1/stream`; backpressure: drop-to-latest for slow clients |
| T-210 | `feat/t210-structured-logging` | `feat: add structlog JSON logging with end-to-end correlation IDs` | HYG correlation | One `correlation_id` traceable from generator to ledger to answer |
| T-211 | `feat/t211-dlq-replay` | `feat(ingestion): add DLQ inspection and replay command` | n/a | Replays fixed messages; idempotent |
| T-212 | `feat/t212-control-totals` | `feat: add control totals across topic and ledger` | n/a | Per batch count and sum match between Kafka offsets range and ledger; mismatch fails `make check-totals` |
| T-215 | `feat/t215-schema-registry` | `feat(events): register schemas with BACKWARD compatibility` | n/a | Redpanda Schema Registry; incompatible change fails CI |
| T-216 | `feat/t216-rebuild-derived` | `feat: add commands to rebuild derived state from the ledger` | n/a | Journal, breaks, and lake rebuildable from Postgres after a rule change; runbook entry |
| T-214 | `docs/t214-architecture-refresh` | `docs: refresh architecture, ADRs, and diagrams after phase 2` | DOC-03, DOC-04, DOC-05 | Diagrams regenerated with the MC-08 skill if installed |

## Phase 3: Analyst and evals (Day 11 to Day 17)

Goal: ask a question, get bound numbers and verifiable citations or a justified refusal; evals gate CI.

| ID | Branch | PR / issue title | REQs | Exit |
|---|---|---|---|---|
| T-301 | `feat/t301-analyst-views` | `feat(analyst): add curated analyst views and read-only role` | SEC-07 | Views in `analyst` schema; integration test: role cannot write even with guard bypassed |
| T-300 | `test/t300-held-out-questions` | `test(evals): add frozen held-out question set` | EVAL-01 | 40 free-form questions written before any prompt work; 10 hand-verified answers |
| T-302 | `feat/t302-query-ir` | `feat(analyst): add constrained query IR and SQL compiler` | SEC-07, QA-04 | ADR-0014 shapes; provenance per shape; filter rendered in words |
| T-302b | `feat/t302b-sql-guard` | `feat(analyst): add hardened SQL guard for the fallback path` | SEC-07 | Threat model 5.3 corpus rejected; generic error codes only |
| T-303 | `feat/t303-llm-interface` | `feat(analyst): add LLM client interface, fake client, cache, and budgets` | QA-09, EVAL-05, SEC-01 | No module test touches network; model IDs from settings |
| T-304 | `feat/t304-router` | `feat(analyst): add rules-first question router` | n/a | Router accuracy measured on golden categories |
| T-305 | `feat/t305-policy-retrieval` | `feat(analyst): add policy corpus, document leaves, and vector retrieval` | SEC-08 | Policy docs hashed into the log as leaves; chunks embedded locally; hybrid retrieval |
| T-306 | `feat/t306-composer-verifier` | `feat(analyst): add slot-bound composer, verifier, and refusal policy` | SEC-08 | Free-number violations rejected; citations limited to evidence set; quote substring check |
| T-307 | `feat/t307-queries-api` | `feat(api): add queries and answers endpoints with rate limits` | URL-01..03, SEC-10 | `POST /api/v1/queries`, `GET /api/v1/answers/{id}` |
| T-308 | `feat/t308-eval-oracle` | `feat(evals): add independent oracle and golden set builder` | EVAL-01 | Oracle shares no code with analyst; smoke set of 20 fixed |
| T-309 | `feat/t309-eval-runner` | `feat(evals): add runner, metrics, thresholds, and reports` | EVAL-02, EVAL-05 | JSON + Markdown report; `eval_run` rows |
| T-310 | `ci/t310-eval-gate` | `ci: add smoke eval gate and nightly full eval` | EVAL-03, EVAL-04, CI-01, CI-03 | Gate fails below thresholds; nightly scheduled pipeline |
| MC-05 | n/a | Anthropic API key with budget | n/a | Only now does a real LLM get called |
| T-311 | `feat/t311-anthropic-client` | `feat(analyst): add Claude client and record first live baseline` | EVAL-04 | Thresholds set from baseline; decision logged |
| T-312 | `feat/t312-analyst-ui` | `feat(web): add analyst page with cited answers and Verify` | UI-03 | Each citation expands to event and proof path; Verify per citation; refused answers explained |
| T-313 | `test/t313-e2e-answer` | `test: add end-to-end test from generator to verified answer` | QA-07 | Pytest e2e using recorded LLM responses |

**RP-2 (end of Day 17): re-plan Phases 4 to 6** with real numbers from evals and load.

## Phase 4: MVP close (Day 17 to Day 19), epic level

| ID | Epic | REQs |
|---|---|---|
| E-401 | Coverage gate >= 85% on core modules enforced in CI | QA-08 |
| E-402 | release-please wired (CHANGELOG from commits); tag `v0.1.0` | GIT-08 |
| E-403 | MkDocs site with mkdocstrings published to GitHub Pages | DOC-06 |
| E-404 | Threat model review against the built system; security review pass with compound-engineering security reviewers | SEC-11 |
| E-405 | Docs refresh: architecture, runbook, configuration, CLAUDE.md | DOC-03, DOC-07 |
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
