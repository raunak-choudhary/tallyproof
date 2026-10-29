# ADR-0011: release-please runs on a minimal GitHub Actions workflow

- Status: Accepted
- Date: 2026-10-26

## Context

CircleCI is locked as the CI system. release-please is required for the CHANGELOG and semver tags. release-please is GitHub-only; it runs either as `googleapis/release-please-action@v5` or as a CLI that needs a GitHub token with write access.

## Decision

A single GitHub Actions workflow, `.github/workflows/release-please.yml`, runs on push to `main` and does nothing but release-please, using the built-in `GITHUB_TOKEN`. **All build, test, lint, eval, and deploy work stays on CircleCI.**

## Reasons

- No long-lived personal access token to store in CircleCI (a smaller set of secrets to protect).
- The release PR flow is native to GitHub.

## Alternative

A CircleCI job on `main` running the release-please CLI with a fine-grained token in a CircleCI context. Viable; rejected for the extra secret.

## Implementation notes (2026-10-29)

- The workflow pins `googleapis/release-please-action` to the commit of release 5.0.0 and grants only `contents: write` and `pull-requests: write`, to that one job.
- Configuration lives in `release-please-config.json` and `.release-please-manifest.json`. The release type is `simple`, with the version also written to `backend/pyproject.toml` and `frontend/package.json`.
- The built-in token can open the release pull request only when the repository allows it: Settings, Actions, General, "Allow GitHub Actions to create and approve pull requests". CircleCI still runs its checks on that pull request, because CircleCI listens to GitHub's webhooks rather than to Actions.
