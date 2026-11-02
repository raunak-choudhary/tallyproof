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
2. Work happens on workstream branches from `main`: `<type>/<area>` (for example `feat/core-verification`). Commit continuously; each commit does one thing.
3. Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <imperative summary>`. Types: feat, fix, docs, test, refactor, perf, build, ci, chore, revert.
4. Open a PR only when the workstream is complete, tests pass, and the branch is rebased on `main` without conflicts. Use the template and walk the reviewer through the commits. PRs are rebase-merged, so every commit lands on `main`.
5. CI must pass. Every PR gets a review pass with comments before merge.
6. Rebase-merge. The PR closes its issue.

## Before pushing

```bash
make lint typecheck test
```

These are the exact commands CI runs.

## Standards

See the [coding standards](docs/coding-standards.md) and the [testing approach](docs/testing.md).
