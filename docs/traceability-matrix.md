# Traceability Matrix

> Every requirement ID in `PROJECT_BRIEF.md` mapped to the phase and task that delivers it. Tasks `T-xxx` are planned in detail; epics `E-xxx` are rolling-wave and will be split into tasks at RP-1 or RP-2. "Continuous" means enforced on every PR by tooling or the definition of done, with the task that installs the enforcement listed.
>
> Requirements in the brief that had **no ID** are given derived IDs (`DRV-*`) at the bottom so nothing is silently dropped.
>
> Status legend: **Planned** (task exists), **Epic** (epic exists, tasks pending), **GAP** (no task: must be resolved before MC-01).

Total brief IDs: 64. Derived IDs: 21. GAPs: **0**. Remapped 2026-10-27 after the design review restructured Phase 1 into 1a (static proof slice) and 1b (live pipeline).

## Run modes

| ID | Requirement (short) | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-OPS-01 | One-command local full stack, no cloud accounts | 1b | T-104, T-123 (`make demo`) | Planned |
| REQ-OPS-02 | Static replay demo, browser-verified proofs, never sleeps | 1a, 5 | T-118, T-121, T-122 (hosted static proof page), E-506 (full replay demo) | Planned / Epic |
| REQ-OPS-03 | Optional live backend, never required | 6 | E-607 | Epic |

## Configuration, secrets, environment

| ID | Requirement | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-SEC-01 | No hardcoded values | 1, continuous | T-126 (settings), T-103 (CI literal check), T-303 (model IDs) | Planned |
| REQ-SEC-02 | Typed pydantic-settings, fail fast | 1b | T-126 | Planned |
| REQ-SEC-03 | `.env` ignored, `.env.example` documented | 0, 1b | T-001 (.gitignore, done), T-126 | Planned |
| REQ-SEC-04 | gitleaks in pre-commit and CI | 1 | T-102, T-103 | Planned |
| REQ-SEC-05 | CI secrets in CircleCI context | 1, 3 | T-103 (MC-04), T-310 | Planned |
| REQ-SEC-06 | Settings split base/local/test/ci | 1b | T-126 | Planned |
| REQ-ENV-01 | Project `.venv` only | 1a, continuous | T-101 (venv), T-102 (Makefile enforces venv) | Planned |
| REQ-ENV-02 | pip-tools `.in` to pinned `.txt` | 1 | T-101 | Planned |
| REQ-ENV-03 | Frontend lockfile pinned | 1 | T-117 | Planned |

## Security

| ID | Requirement | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-SEC-07 | Read-only role, SELECT allowlist, limits, timeouts | 1b, 3 | T-104 (roles script), T-112b (grants), T-301, T-302 (query IR), T-302b (hardened guard) | Planned |
| REQ-SEC-08 | Untrusted data, prompt-injection defense | 1a, 1b, 3 | T-110 (validation), T-111 (injection test data only), T-113d (DLQ), T-305, T-306 (defenses) | Planned |
| REQ-SEC-09 | Synthetic data only | 1 | T-111 (fixed fake word lists) | Planned |
| REQ-SEC-10 | Rate limiting and validation on public endpoints | 1b, 3 | T-115b, T-307 | Planned |
| REQ-SEC-11 | Threat model doc | 0, 4 | T-002 (draft), E-404 (review against built system) | Planned / Epic |

## Git workflow

| ID | Requirement | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-GIT-01 | Conventional Commits | 0, 1a, continuous | T-003 (done), T-102 (commit-msg hook), T-103 (CI lints every commit, required because PRs are rebase-merged) | Planned |
| REQ-GIT-02 | Branch per task | continuous | Plan rule section 0; every task | Planned |
| REQ-GIT-03 | PRs only, protected main, squash | 0, 1a | MC-03 (done), T-103 (`ci-gate` required check) | Planned |
| REQ-GIT-04 | Small PRs, PR template | 0 | T-003 | Done |
| REQ-GIT-05 | Issues per task, milestones | 0 | T-004 | Planned |
| REQ-GIT-06 | Review pass with comments before merge | continuous | Definition of done; compound-engineering review agents | Planned |
| REQ-GIT-07 | Pre-commit: ruff, format, mypy, commit lint, gitleaks | 1 | T-102 | Planned |
| REQ-GIT-08 | CHANGELOG via release-please, semver tags | 4, 6 | E-402 (`v0.1.0`), E-608 (`v1.0.0`) | Epic |
| REQ-GIT-09 | LICENSE, SECURITY, CODEOWNERS, CONTRIBUTING, templates, Dependabot | 0 | T-001, T-003 | Done |

## Code quality and testing

| ID | Requirement | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-QA-01 | Google docstrings, why-comments | 1, continuous | T-102 (ruff pydocstyle `google` convention), every task | Planned |
| REQ-QA-02 | mypy strict with django-stubs | 1 | T-102 | Planned |
| REQ-QA-03 | ruff, zero warnings | 1 | T-102, T-103 | Planned |
| REQ-QA-04 | Unit + Hypothesis tests on pure logic | 1, 2, 3 | T-105..T-108, T-204, T-205, T-302 | Planned |
| REQ-QA-05 | Module tests per app, faked deps | 1b..3, 4 | T-113a..d, every app task, E-406 audit | Planned |
| REQ-QA-06 | Testcontainers integration | 1b | T-116, T-116b | Planned |
| REQ-QA-07 | E2E generator-to-answer; Playwright | 3, 5 | T-116 (partial), T-313, E-507 | Planned / Epic |
| REQ-QA-08 | 85% coverage on core | 1, 4 | T-106 (module gate), E-401 (CI gate) | Planned / Epic |
| REQ-QA-09 | No real LLM in unit/module tests | 3 | T-303 (+ network-blocking pytest fixture) | Planned |
| REQ-QA-10 | Frontend Vitest, ESLint, Prettier, tsc | 1 | T-117 | Planned |

## Evals

| ID | Requirement | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-EVAL-01 | Golden set from ground truth | 2, 3 | T-201 (labels), T-300 (held-out set), T-308 | Planned |
| REQ-EVAL-02 | Citation P/R, numeric exactness, anomaly recall, refusal, faithfulness | 3 | T-309 | Planned |
| REQ-EVAL-03 | Smoke on PR, full nightly | 3 | T-310 | Planned |
| REQ-EVAL-04 | CI fails on regression | 3 | T-310, T-311 (thresholds) | Planned |
| REQ-EVAL-05 | Token budgets and caching | 3 | T-303, T-309 | Planned |
| REQ-EVAL-06 | README results table refreshed by CI | 5 | E-505, E-510 | Epic |

## CircleCI

| ID | Requirement | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-CI-01 | lint, typecheck, unit (parallel), integration, eval gate, build | 1a, 1b, 3 | T-103, T-116b, T-310 (build job in T-117 and T-122) | Planned |
| REQ-CI-02 | Frontend jobs separate | 1 | T-117 | Planned |
| REQ-CI-03 | Coverage and eval reports as artifacts | 1, 3 | T-103, T-310 | Planned |
| REQ-CI-04 | CI mirrors `make` targets | 1 | T-102, T-103 | Planned |

## Documentation

| ID | Requirement | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-DOC-01 | README structure incl. hero diagram, GIF | 1a, 1b, 5 | T-120, T-120b, E-510 (hero, GIF) | Planned / Epic |
| REQ-DOC-02 | README per app and frontend feature | 1b, continuous | T-120b, every new app task | Planned |
| REQ-DOC-03 | Architecture doc | 0, 2, 4 | T-002, T-214, E-405 | Planned |
| REQ-DOC-04 | C4 context, container, sequence, ER diagrams via diagram skill | 0, 2 | T-002 (Mermaid drafts), T-214 (skill, after MC-08) | Planned (blocked on MC-08) |
| REQ-DOC-05 | ADRs for decisions and deviations | 0, continuous | T-002 | Planned |
| REQ-DOC-06 | MkDocs site | 4 | E-403 | Epic |
| REQ-DOC-07 | CLAUDE.md current | 0, continuous | T-002, E-405 | Planned |

## URL and API

| ID | Requirement | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-URL-01 | Kebab-case, nouns, plural, no raw IDs | 1b, 3 | T-115a, T-115b, T-206, T-307 | Planned |
| REQ-URL-02 | Prefixed public IDs | 1 | T-105 | Planned |
| REQ-URL-03 | `/api/v1` versioning | 1b | T-115a | Planned |
| REQ-URL-04 | API returns proofs, client verifies | 1a, 1b, 2 | T-118, T-115a, T-207 | Planned |
| REQ-URL-05 | `/healthz`, `/readyz` | 1b | T-104 | Planned |

## Frontend

| ID | Requirement | Phase | Task(s) | Status |
|---|---|---|---|---|
| REQ-UI-01 | Motion landing page | 5 | E-501 | Epic |
| REQ-UI-02 | Live stream view over WebSockets | 2, 5 | T-209, E-502 | Planned / Epic |
| REQ-UI-03 | Analyst with expandable citations and Verify | 1a, 3, 5 | T-119 (citation component), T-312 (analyst), E-503 | Planned / Epic |
| REQ-UI-04 | Tamper demo | 1, 2, 5 | T-119, T-208, E-504 | Planned / Epic |
| REQ-UI-05 | Eval dashboard | 5 | E-505 | Epic |
| REQ-UI-06 | Responsive, accessible, light and dark | 1, 5 | T-117, T-119, E-511 | Planned / Epic |

## Derived requirements (no ID in brief)

| ID | Source in brief | Requirement | Task(s) | Status |
|---|---|---|---|---|
| DRV-FLOW-01 | 5.1 step 1 | Seeded generator with labeled anomalies | T-111, T-201 | Planned |
| DRV-FLOW-02 | 5.1 step 2, 3.1 | Kafka ingestion with own Bloom filter dedupe | T-108, T-113c | Planned |
| DRV-FLOW-03 | 5.1 step 3 | Reconciliation with breaks | T-205, T-206 | Planned |
| DRV-FLOW-04 | 5.1 step 4 | Append-only ledger in Postgres | T-112, T-113a | Planned |
| DRV-FLOW-05 | 5.1 step 5, 3.1 | Own Merkle tree, batches, proofs | T-106, T-107, T-109, T-114, T-121 | Planned |
| DRV-FLOW-06 | 5.1 step 6 | Router: SQL for numeric, vectors for policy, refusal | T-302, T-302b, T-303..T-306 | Planned |
| DRV-FLOW-07 | 5.1 step 7 | Evals against generator ground truth | T-308, T-309 | Planned |
| DRV-ADR-01 | 5.2 | ADR-0001 SQL over NoSQL | T-002 | Planned |
| DRV-ADR-02 | 2.2 | QLDB gap featured in ADR and README | T-002 (ADR-0001), T-120 | Planned |
| DRV-README-01 | 2.4 | Prior art and differentiation incl. answerproof | T-120 | Planned |
| DRV-README-02 | 2.2, 2.3 | Only verified primary sources cited | T-002 (verified source list), T-120 | Planned |
| DRV-README-03 | 5.3 | README states which mode the public link runs | E-506 | Epic |
| DRV-NAME-01 | 4 | Naming analysis, top 3, ADR, apply everywhere | T-002 (ADR-0006), MC-02 | Planned |
| DRV-HYG-01 | 14 | Makefile targets up, down, test, lint, typecheck, eval, seed, replay, docs | T-102 (lint, typecheck, test), T-104 (up, down), T-111 (seed), T-123 (demo), T-309 (eval), T-121 and E-506 (replay), E-403 (docs) | Planned |
| DRV-HYG-02 | 14 | Fixed seeds, reproducible scenarios | T-111 | Planned |
| DRV-HYG-03 | 14 | Schema change = own migration PR | T-112, T-203, T-301 | Planned |
| DRV-HYG-04 | 14 | Correlation ID from ingestion to answer | T-210 | Planned |
| DRV-HYG-05 | 14 | Honest, measured scale | E-509 | Epic |
| DRV-SCOPE-01 | 13 | MVP-not-green rule pauses MLP | Plan Phase 4 rule | Planned |
| DRV-TOOL-01 | 12.1 | Diagram skills installed only via MC-08 | T-214 | Planned (blocked on MC-08) |
| DRV-TOOL-02 | 12.1 | Frontend design skill available | Verified available 2026-10-26 | Done |
