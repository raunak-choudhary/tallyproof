# 10. Code Standards

## Python

- Python 3.12, always inside `backend/.venv` (REQ-ENV-01). The Makefile refuses to run Python targets outside the venv.
- ruff for lint and format, zero warnings on `main` (REQ-QA-03). Rule sets: `E, F, W, I, B, UP, SIM, N, D (google convention), S (bandit subset), DJ, PT, RUF, ANN`.
- mypy `strict = true` with django-stubs (REQ-QA-02). No `Any` in `core`. `# type: ignore` requires an error code and a reason comment.
- Google-style docstrings on every public module, class, and function (REQ-QA-01). Inline comments explain **why**; a comment that restates the code is a review finding.
- Money is `Decimal` via `core.money.Money`; floats for money are a review blocker.
- Time is timezone-aware UTC (`datetime.now(tz=UTC)` via an injectable clock).
- No configuration literals: thresholds, URLs, model IDs, sizes come from `config.env.Settings` (REQ-SEC-01).
- Errors: domain exceptions in each app's `errors.py`; API maps them to RFC 9457 responses.
- Dependencies: add to `requirements.in` or `requirements-dev.in`, then `make deps` (pip-compile with hashes). Never `pip install` ad hoc (REQ-ENV-02).

## TypeScript

- `strict: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true`.
- ESLint 10 flat config + typescript-eslint, Prettier, `tsc --noEmit` (REQ-QA-10).
- No `any`; `unknown` plus narrowing at boundaries; API types generated from OpenAPI.
- Components: server components by default; client components only where interaction requires it.

## Git (REQ-GIT-01 to 06)

- Conventional Commits: `<type>(<scope>): <imperative summary>`, types `feat, fix, docs, test, refactor, perf, build, ci, chore, revert`. Scopes: `core, events, generator, ingestion, ledger, recon, analyst, evals, lake, realtime, api, web, infra, ci, docs`.
- Body explains what and why. No AI co-author trailers (owner preference).
- Branch `<type>/<task-id>-<slug>`; PR title equals the squash commit message; PR closes its issue.
- Review pass: at least one round of review comments on every PR before merge, covering correctness, tests, docs, security.

## Naming

- Public IDs prefixed (REQ-URL-02). Internal integer keys never leave the service.
- Kafka topics `<domain>.<entity>.<stage>.v<major>`.
- Env vars `UPPER_SNAKE`, grouped by prefix (`DB_`, `KAFKA_`, `MERKLE_`, `LLM_`, `EVAL_`).

## Writing

- No em dashes in docs, comments, commit messages, or PR text (owner preference).
- Public-facing text reads as written by a person: no emoji headers, no audit-speak.
