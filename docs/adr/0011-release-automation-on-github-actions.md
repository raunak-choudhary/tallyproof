# ADR-0011: release-please runs on a minimal GitHub Actions workflow

- Status: Proposed (MC-01)
- Date: 2026-10-26
- Zone: Clarification of locked items (CircleCI for CI, release-please for CHANGELOG)

## Context

CircleCI is locked as the CI system. release-please is required for the CHANGELOG and semver tags. release-please is GitHub-only; it runs either as `googleapis/release-please-action@v5` or as a CLI that needs a GitHub token with write access.

## Decision

A single GitHub Actions workflow, `.github/workflows/release-please.yml`, runs on push to `main` and does nothing but release-please, using the built-in `GITHUB_TOKEN`. **All build, test, lint, eval, and deploy work stays on CircleCI.**

## Reasons

- No long-lived personal access token to store in CircleCI (smaller secret surface, REQ-SEC-05).
- The release PR flow is native to GitHub.

## Alternative

A CircleCI job on `main` running the release-please CLI with a fine-grained token in a CircleCI context. Viable; rejected for the extra secret.
