# Contributing to Tallyproof

Thank you for looking at the code. The project is complete at version 1.1.0, and fixes, clearer documentation and better tests are welcome. This page explains how a change goes from an idea to `main`.

## Before you start

Open an issue first, even for a small fix, so the change has a home and a number. If you are unsure whether something is a bug, the [threat model](docs/threat-model.md) and the [limitations](docs/limitations.md) say what the system promises and what it deliberately leaves out.

## Setup

The README's [Running it locally](README.md#running-it-locally) section walks through the tools, environments and configuration step by step. In short:

```bash
make venv                                  # backend/.venv with every dependency pinned
cd backend && .venv/bin/pre-commit install --hook-type pre-commit --hook-type commit-msg && cd ..
cd frontend && pnpm install --frozen-lockfile && cd ..
```

Never install Python packages outside `backend/.venv`. To add a dependency, edit `requirements.in` or `requirements-dev.in`, run `make deps`, and commit both the `.in` and the `.txt` files.

## How a change lands

1. **Branch from `main`**, named `<type>/<area>`, for example `fix/verifier-rounding` or `docs/runbook-linux`.
2. **Commit small and often.** Each commit does one thing and follows [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <imperative summary>`. Types: feat, fix, docs, test, refactor, perf, build, ci, chore, revert. The commit-message hook checks the format.
3. **Run the checks before pushing.** These are the exact commands CI runs:

   ```bash
   make lint typecheck test      # backend
   make web-check                # web app
   make docs-build               # documentation site, strict
   ```

4. **Open a pull request when the branch is complete** and rebased on `main` without conflicts. Describe what changed and why, and walk the reviewer through the commits. One pull request in CI at a time.
5. **CI must be green**: lint, strict types, unit, Spark and integration tests, coverage, the browser suite with accessibility checks, the documentation build, the dependency audit, the commit-message check and the secret scan.
6. **Rebase merge.** Every commit lands on `main` as it was reviewed. Branches are kept after merging; nothing is force-pushed.

## Standards

The [coding standards](docs/coding-standards.md) cover Python and TypeScript style, naming, and the rules that bite (no hardcoded literals, no model change without a migration). The [testing approach](docs/testing.md) explains what each suite covers and how the shared test vectors keep the Python and browser verifiers identical. The [frontend guidelines](docs/frontend-guidelines.md) cover tokens, both themes, responsiveness and motion.

## Two things never to do

- Never commit a `.env` file, a key, or anything from `secrets/`. The pre-commit scanner and GitHub's push protection will refuse, and the history is scanned in CI.
- Never regenerate the signed replay bundle under `frontend/public/replay/` from the gold data. It is witnessed by an outside timestamp; a new bundle needs a new key and a new witness, as the [runbook](docs/runbook.md) describes.
