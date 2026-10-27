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

Goal: approved plan, named project, protected repo, issues on a board.

| ID | Branch | PR / issue title | REQs | Exit |
|---|---|---|---|---|
| T-001 | (initial commit) | `chore: initialize repository` | GIT-09 (partial) | Repo created after MC-02. Only `README.md` stub, `LICENSE` (MIT), `.gitignore`. The initial commit is the only direct push to `main`; an empty repo has nothing to open a PR against |
| MC-03 | n/a | Branch protection on `main` | GIT-03 | Require PR, require status checks (added once CI exists), linear history, squash only, no force push. No required approvals (solo repo cannot self-approve) |
| T-002 | `docs/t002-planning-docs` | `docs: add phase 0 planning documents and ADRs` | DOC-05, DOC-07, all planning docs | All Section 9.1 docs merged. Large docs-only PR is an accepted exception to the 400-line target, logged in decisions log |
| T-003 | `chore/t003-repo-governance` | `chore: add governance files and GitHub templates` | GIT-04, GIT-09 | SECURITY.md, CODEOWNERS, CONTRIBUTING.md, PR template, issue templates (task, bug), Dependabot config, `.editorconfig` |
| T-004 | `chore/t004-issue-bootstrap` | `chore: add script to create milestones, labels, and issues from the plan` | GIT-05 | `scripts/github/bootstrap.py` parses this file and creates milestones, labels, issues idempotently via `gh`. Run once; issues exist for every task ID below |

## Phase 1: Proof slice (Day 1 to Day 4)

Goal: a reviewer can clone, run one command, watch events become a signed Merkle log, open an event in the browser, click Verify, edit it, and watch Verify fail. CI green. README tells the truth about status. **This is the first thing outside reviewers will see, so it must be small, real, and polished.**

| ID | Branch | PR / issue title | REQs | Exit |
|---|---|---|---|---|
| T-101 | `build/t101-backend-skeleton` | `build(backend): scaffold Django 5.2 project with typed settings` | ENV-01, ENV-02, SEC-01, SEC-02, SEC-03, SEC-06 | `.venv`, pip-tools `requirements*.in/.txt` committed, `config/settings/{base,local,test,ci}.py`, `config/env.py` fails fast on missing vars, `.env.example` documented |
| T-102 | `build/t102-quality-tooling` | `build: add ruff, mypy strict, pytest, pre-commit, and Makefile` | QA-02, QA-03, GIT-07, SEC-04, CI-04 | `make lint typecheck test` pass on skeleton; pre-commit runs ruff, ruff-format, mypy, gitleaks, conventional commit check |
| T-103 | `ci/t103-circleci-pipeline` | `ci: add CircleCI pipeline for lint, typecheck, and unit tests` | CI-01 (partial), CI-03, CI-04, SEC-04, SEC-05 | Pipeline runs `make` targets; unit tests split across parallel containers; coverage XML stored as artifact. **MC-04** here; then add required checks to branch protection |
| T-104 | `build/t104-local-stack` | `build(infra): add compose stack with Redpanda, Postgres, Redis` | OPS-01, URL-05, SEC-07 (roles) | `make up` starts Redpanda + Console, Postgres 16 + pgvector, Redis; `roles.sql` creates app, analyst, owner roles; topic bootstrap script; `/healthz` and `/readyz` (broker, DB, cache) |
| T-105 | `feat/t105-canonical-ids-money` | `feat(core): add canonical JSON, prefixed IDs, and money type` | URL-02, QA-01, QA-04 | RFC 8785 serializer with test vectors from the RFC; ULID IDs with prefixes; Decimal money; `testdata/vectors/*.json` generated for the TS mirror |
| T-106 | `feat/t106-merkle-log` | `feat(core): add RFC 9162 Merkle log with inclusion proofs` | QA-04, QA-08 | Root, inclusion proof, verify; Hypothesis: any tampered leaf or path element fails; RFC test vectors pass; coverage >= 95% for module |
| T-107 | `feat/t107-consistency-proofs` | `feat(core): add Merkle consistency proofs` | QA-04 | Consistency proof and verify; property: proof between any m <= n verifies, and fails after any rewrite of the first m leaves |
| T-108 | `feat/t108-bloom-filter` | `feat(core): add Bloom filter with sizing math` | QA-04 | Optimal m and k from n and target FPR; property: never a false negative; statistical test: measured FPR within bound at fixed seed; serialization for snapshots |
| T-109 | `feat/t109-signed-checkpoints` | `feat(core): add signed checkpoints in C2SP format` | SEC-01 | Ed25519 sign and verify; key generation command writes to stdout only (operator pastes into `.env`); checkpoint parse rejects malformed bodies |
| T-110 | `feat/t110-event-schemas` | `feat(events): add event envelope schemas and topic registry` | SEC-08 (input validation) | Pydantic models, discriminated payloads, JSON Schema export to `schemas/`, topic registry constants from settings |
| T-111 | `feat/t111-generator-v1` | `feat(generator): add seeded scenario generator with first anomalies` | HYG seeds | Same seed yields byte-identical output; anomalies `duplicate_delivery`, `orphan_payment`, `amount_mismatch`, `injection_memo`; `manifest.jsonl` separate from events; produces to Redpanda |
| T-112 | `feat/t112-ledger-schema` | `feat(ledger): add append-only ledger schema and migrations` | SEC-07, HYG migration | Tables `ledger_event`, `ledger_batch`, `consumer_offset`, `dedupe_rejection`, `outbox`; append-only triggers; grant test proves app role cannot UPDATE/DELETE |
| T-113 | `feat/t113-ingestion-worker` | `feat(ingestion): add effectively-once consumer with Bloom dedupe and DLQ` | QA-05, QA-06 | Validation to DLQ; Bloom fast path plus UNIQUE fallback; offsets stored in same transaction; restart test shows no duplicates and no gaps |
| T-114 | `feat/t114-checkpointer` | `feat(ledger): add size-or-time batch checkpointer and witness export` | ADR-0003 | Batches close on size or age; signed checkpoints stored; `witness/checkpoints.jsonl` export command |
| T-115 | `feat/t115-proof-api` | `feat(api): add events, proofs, batches, and checkpoint endpoints` | URL-01..04, SEC-10 | DRF + drf-spectacular OpenAPI; RFC 9457 errors; throttling baseline; API returns proofs, never verdicts |
| T-116 | `test/t116-integration-slice` | `test: add Testcontainers integration test from generator to proof` | QA-06, QA-07 (partial) | Real Redpanda + Postgres containers; generate, ingest, checkpoint, fetch proof, verify in Python |
| T-117 | `build/t117-frontend-skeleton` | `build(web): scaffold Next.js app with themes and quality tooling` | QA-10, UI-06, ENV-03, CI-02 | TS strict, Tailwind, shadcn/ui, CSS variable tokens for light and dark, ESLint, Prettier, Vitest; `NEXT_PUBLIC_API_URL` from env; CircleCI web jobs |
| T-118 | `feat/t118-web-verifier` | `feat(web): add browser verification library mirrored from core` | OPS-02, URL-04 | JCS, leaf hash, inclusion verify, checkpoint signature verify in TS; passes the shared cross-language vectors |
| T-119 | `feat/t119-event-verify-page` | `feat(web): add event page with Verify and tamper toggle` | UI-03 (partial), UI-04 (partial), UI-06 | `/ledger/events/[eventId]` shows event, proof path, Verify; "edit a field" toggle makes Verify fail with the failing level shown; keyboard accessible; both themes |
| T-120 | `docs/t120-readme-v1` | `docs: write README v1 and app READMEs` | DOC-01 (partial), DOC-02 | Pitch, status banner (what works today), quickstart in three commands, verified "why this exists", related work including answerproof, architecture summary; README in every app |

**RP-1 (end of Day 4): re-plan.** Review what was slower or faster than expected, update Phases 2 to 6, log changes. Run `/graphify` on the codebase for the first time and commit `graphify-out/GRAPH_REPORT.md` if useful.

## Phase 2: Pipeline depth (Day 5 to Day 9)

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
| T-213 | `ci/t213-integration-job` | `ci: run Testcontainers integration tests in CircleCI` | CI-01, QA-06 | Machine executor job after unit tests; artifacts stored |
| T-214 | `docs/t214-architecture-refresh` | `docs: refresh architecture, ADRs, and diagrams after phase 2` | DOC-03, DOC-04, DOC-05 | Diagrams regenerated with the MC-08 skill if installed |

## Phase 3: Analyst and evals (Day 9 to Day 15)

Goal: ask a question, get bound numbers and verifiable citations or a justified refusal; evals gate CI.

| ID | Branch | PR / issue title | REQs | Exit |
|---|---|---|---|---|
| T-301 | `feat/t301-analyst-views` | `feat(analyst): add curated analyst views and read-only role` | SEC-07 | Views in `analyst` schema; integration test: role cannot write even with guard bypassed |
| T-302 | `feat/t302-sql-guard` | `feat(analyst): add AST SQL guard with provenance derivation` | SEC-07, QA-04 | Malicious corpus rejected; LIMIT injection; provenance query derived for aggregates or claim marked unverifiable |
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

**RP-2 (end of Day 15): re-plan Phases 4 to 6** with real numbers from evals and load.

## Phase 4: MVP close (Day 15 to Day 17), epic level

| ID | Epic | REQs |
|---|---|---|
| E-401 | Coverage gate >= 85% on core modules enforced in CI | QA-08 |
| E-402 | release-please wired (CHANGELOG from commits); tag `v0.1.0` | GIT-08 |
| E-403 | MkDocs site with mkdocstrings published to GitHub Pages | DOC-06 |
| E-404 | Threat model review against the built system; security review pass with compound-engineering security reviewers | SEC-11 |
| E-405 | Docs refresh: architecture, runbook, configuration, CLAUDE.md | DOC-03, DOC-07 |
| E-406 | Module test audit: every Django app has module tests with faked dependencies | QA-05 |

Rule from the brief: if MVP is not green by end of Week 3, MLP pauses.

## Phase 5: MLP experience and data depth (Day 17 to Day 25), epic level

| ID | Epic | REQs |
|---|---|---|
| E-501 | Motion landing page: event flows through stream, hashed into tree, appears as verified citation | UI-01 |
| E-502 | Live stream dashboard | UI-02 |
| E-503 | Citation proof visualization: animated audit path with Verify | UI-03 |
| E-504 | Tamper ladder demo, levels 1 to 4, in browser | UI-04 |
| E-505 | Eval dashboard across runs, including naive baseline column | UI-05, EVAL-06 |
| E-506 | Replay bundle export and static build; Vercel project (**MC-06**); README states which mode the link runs | OPS-02 |
| E-507 | Playwright flows: landing, verify, tamper, analyst, evals | QA-07 |
| E-508 | Parquet lake sink to S3-compatible store; control totals extended to lake | (data signal) |
| E-509 | Measured load-test report: throughput, lag, p50/p95/p99, hardware stated | HYG-05 |
| E-510 | README hero diagram (MC-08 skill), tamper GIF, nightly eval table refresh via bot PR | DOC-01, EVAL-06 |
| E-511 | Accessibility pass: keyboard paths, contrast, reduced motion | UI-06 |

## Phase 6: Nice-to-have and v1.0.0 (Day 25 to Day 30), epic level

| ID | Epic |
|---|---|
| E-601 | Count-Min Sketch heavy hitters for `vendor_burst` |
| E-602 | Schema evolution v1 to v2 with registry compatibility checks |
| E-603 | DuckDB batch reconciliation over 10M+ rows in the lake; streaming versus batch comparison |
| E-604 | Merkle-sum tree for provable totals |
| E-605 | OpenTelemetry tracing |
| E-606 | AWS reference architecture IaC sketch (not deployed) |
| E-607 | Optional live backend (**MC-07**), never load-bearing (OPS-03) |
| E-608 | Tag `v1.0.0` |

## Re-planning checkpoints

| ID | When | Inputs | Output |
|---|---|---|---|
| RP-1 | End of Phase 1 | Actual velocity, CI time, any design surprises | Updated Phases 2 to 6, decisions logged |
| RP-2 | End of Phase 3 | First live eval numbers, latency, cost | Phases 4 to 6 broken into tasks; thresholds set |
| RP-3 | End of Phase 5 | Remaining days | Pick which Nice-to-haves to do |
