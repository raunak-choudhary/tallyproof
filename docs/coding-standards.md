# Coding standards

## Python

- Python 3.12, always inside `backend/.venv`. The Makefile refuses to run Python targets outside it.
- Dependencies go in `requirements.in` or `requirements-dev.in`. `make deps` compiles them into pinned files with hashes, and both the `.in` and `.txt` files are committed. Nothing is installed with a bare `pip install`.
- ruff handles linting and formatting, and `main` has zero warnings. Enabled rule sets: `E`, `F`, `W`, `I`, `B`, `UP`, `SIM`, `N`, `D` with the Google convention, a subset of `S`, `DJ`, `PT`, `RUF`, and `ANN`.
- mypy runs in strict mode with django-stubs. `tallyproof_core` has no `Any`. A `# type: ignore` needs an error code and a comment explaining why.
- Every public module, class, and function has a Google-style docstring. Inline comments explain why something is done. A comment that only restates the code gets removed in review.
- Money is always `Decimal` through the `Money` type. Floats for money are a review blocker.
- Times are timezone-aware UTC and come from an injectable clock, so tests can control them.
- Thresholds, URLs, model IDs, and sizes come from the typed settings, never from literals in code.
- Each app defines its own exceptions, and the API maps them to RFC 9457 problem responses.

## TypeScript

- `strict`, `noUncheckedIndexedAccess`, and `exactOptionalPropertyTypes` are all on.
- ESLint with a flat config and typescript-eslint, Prettier, and `tsc --noEmit` run in CI.
- No `any`. Data crossing a boundary is typed `unknown` and narrowed. API types are generated from the OpenAPI schema.
- Components are server components unless they need interaction.

## Git

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <imperative summary>`, where the type is one of `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, or `revert`. The body explains what changed and why.
- Each commit does one thing. A documentation commit contains documentation. A correction to earlier work is its own `fix` or `refactor` commit, so the history shows how the code got where it is.
- Work happens on one branch per major area, named `<type>/<area>`, for example `feat/data-pipeline` or `feat/web-app`. A branch is merged once its area of work is finished, its tests pass, CI is green, and it's rebased on `main` with no conflicts.
- Pull requests are rebase-merged, so every commit lands on `main` and every commit has to pass the commit message check, not just the pull request title.
- When one branch needs code from another that isn't merged yet, it's stacked on top of that branch and rebased onto `main` after the first one merges. Sibling branches are never merged into each other.
- Every pull request gets a review pass with written comments before it merges.
- Releases come from the commit history. A GitHub Actions workflow runs [release-please](https://github.com/googleapis/release-please) on every push to `main` and keeps a release pull request open with the next version and its changelog: `feat` commits raise the minor version before 1.0, `fix` commits the patch version, and a breaking change the minor version until 1.0. Merging that pull request writes `CHANGELOG.md`, sets the version in `backend/pyproject.toml` and `frontend/package.json`, and tags the release.

## Naming

- Public IDs carry a type prefix, such as `evt_` or `ans_`. Internal integer keys never leave the service.
- Kafka topics are named `<domain>.<entity>.<stage>.v<major>`.
- Environment variables are upper snake case and grouped by prefix: `DB_`, `KAFKA_`, `MERKLE_`, `LLM_`, `EVAL_`, `DATA_`, `SPARK_`.

## Writing

- Documentation is written for people. It uses plain sentences, specific numbers with sources, and no marketing language.
- No em dashes in documentation, comments, commit messages, or pull request text. There's one exception the code depends on: the C2SP signed-note format starts each signature line with U+2014, so the checkpoint code in Python and TypeScript must produce and parse that exact character. A unit test checks it, so a style cleanup can't break signatures by accident.
