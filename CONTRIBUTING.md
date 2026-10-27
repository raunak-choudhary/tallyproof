# Contributing

## Setup

```bash
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
make deps-sync          # installs pinned requirements into .venv
pre-commit install --hook-type pre-commit --hook-type commit-msg
cd ../frontend && pnpm install --frozen-lockfile
```

Never install Python packages outside `.venv`. Add dependencies to `requirements.in` or `requirements-dev.in`, then run `make deps` and commit both `.in` and `.txt` files.

## Workflow

1. Every change starts from a GitHub issue.
2. Branch from `main`: `<type>/<task-id>-<slug>` (for example `feat/t106-merkle-log`).
3. Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <imperative summary>`. Types: feat, fix, docs, test, refactor, perf, build, ci, chore, revert.
4. Open a PR using the template. Keep it under about 400 changed lines. Each commit should do one thing, because PRs are rebase-merged and every commit lands on `main`.
5. CI must pass. Every PR gets a review pass with comments before merge.
6. Rebase-merge. The PR closes its issue.

## Before pushing

```bash
make lint typecheck test
```

These are the exact commands CI runs.

## Standards

See `docs/10-code-standards.md` and `docs/09-testing-strategy.md`.
