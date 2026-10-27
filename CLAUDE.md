# CLAUDE.md: Tallyproof

Project-level source of truth for coding agents and contributors. Where it conflicts with any shared or global agent rules, this file wins for this repo.

## 1. What this is

Streaming financial ledger plus AI analyst. Every claim cites a source event with an RFC 9162 Merkle inclusion proof that the browser verifies against an Ed25519-signed, externally witnessed checkpoint. Evals use exact generator ground truth. The original project brief is kept outside the repo; the docs below supersede it.

## 2. Current phase

**Phase 0: planning docs merged and revised after design review. Name decided: Tallyproof (ADR-0006). Awaiting MC-01 (plan approval) after the data-source discussion.** No application code until approved. Next task after approval: T-004, then Phase 1a (T-101).

## 3. Docs map

| Need | File |
|---|---|
| Scope, users, metrics | `docs/01-prd.md` |
| Screens and journeys | `docs/02-app-flow.md` |
| Versions and why | `docs/03-tech-stack.md`, evidence in `docs/research/stack-versions-2026-10.md` |
| UI tokens, motion, a11y | `docs/04-frontend-guidelines.md` |
| Layout, topics, schemas, API, DB | `docs/05-backend-structure.md` |
| Tasks, branches, phases | `docs/06-implementation-plan.md` |
| Architecture, tamper ladder, limits | `docs/07-architecture.md` |
| Evals | `docs/08-eval-spec.md` |
| Tests | `docs/09-testing-strategy.md` |
| Code and git standards | `docs/10-code-standards.md` |
| Threat model | `docs/11-security-and-threat-model.md` |
| Decisions, risks, open questions | `docs/12-risks-and-decisions-log.md` |
| Every env var | `docs/13-configuration.md` |
| Run, reset, debug | `docs/14-runbook.md` |
| AWS mapping | `docs/15-aws-reference-architecture.md` |
| Requirement coverage | `docs/traceability-matrix.md` |
| ADRs | `docs/adr/` |
| Verified citations | `docs/research/verified-sources.md` |

## 4. Commands (become real during Phase 1)

`make up | down | reset | deps | deps-sync | lint | typecheck | test | test-integration | eval | seed | replay | docs | keygen | tamper | verify-witness | check-totals`. CI runs the same targets (REQ-CI-04).

## 5. Non-negotiables

1. No hardcoded config: everything via `backend/config/env.py` (pydantic-settings) from `.env`. Model IDs included.
2. Python only inside `backend/.venv`; deps via `requirements*.in` then `make deps`; commit `.in` and `.txt`.
3. One task = one issue. Branches are workstreams (`<type>/<area>`); commit continuously; one PR per completed, green, conflict-free workstream (plan section 0); stacked branches for cross-workstream dependencies. Never push to `main` (exception: the very first commit). Rebase-merge after CI green and a review pass with comments, so every commit stays visible on `main`. Keep merged branches.
4. Conventional Commits. No AI co-author trailer. No em dashes anywhere.
5. Tests first for `core`, `ledger`, `ingestion`, `reconciliation`, `analyst/sql_guard`, `analyst/verifier`. Unit/module tests never call a real LLM.
6. Server returns proofs, never verdicts. Client verifies.
7. Labels never inside events. Eval oracle never imports analyst code.
8. Money is Decimal / decimal strings. Never floats.
9. Both themes and responsive (375/768/1280) from the first component. WebSockets for realtime, no polling.
10. Manual checkpoints (MC-01..08 in the brief): stop and ask Raunak. Never invent credentials or install commands.
11. Update this file and `docs/12-risks-and-decisions-log.md` as decisions happen.

## 6. Workflow decisions

- PR workflow above replaces any "push to main" habit (owner decision 2026-10-26).
- Rebase-merge keeps every Conventional Commit visible on `main` (decision log 2026-10-27).

## 7. Codex / fresh-agent handoff

To be written before any handoff: exact file paths, import paths, event types, exit conditions. Read this file, then `graphify-out/GRAPH_REPORT.md` (generated after Phase 1).
