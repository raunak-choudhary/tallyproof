# ADR-0020: GitHub Pages for the public demo, deployed by GitHub Actions

- Status: Accepted
- Date: 2026-10-28

## Context

The public demo is a static export with every proof checked in the browser ([ADR-0005](0005-replay-mode-public-demo.md)), so any static host works. The plan named Vercel, with GitHub Pages as the fallback that needs no new account. [ADR-0011](0011-release-automation-on-github-actions.md) keeps build, test, and deploy work on CircleCI, and allows GitHub Actions only where it avoids storing a long-lived GitHub token.

## Decision

Publish the demo on GitHub Pages at `https://raunak-choudhary.github.io/tallyproof/`. A single workflow, `.github/workflows/pages.yml`, builds the static export and deploys it on every push to `main` that touches `frontend/`. It uses the built-in token with `pages: write` and `id-token: write` on the deploy job only, and every action is pinned to a commit.

The site is served under `/tallyproof/`, so the build reads `NEXT_PUBLIC_BASE_PATH` and the replay bundle location follows it. The pinned verifier key comes from the repository variable `PINNED_VERIFIER_KEY`. It's a public key, kept out of the workflow file so the file holds no configuration values.

## Reasons

- No new service or account. The repository already holds everything the site needs.
- Deploying from CircleCI would need a GitHub token with write access stored in CircleCI, the same trade-off ADR-0011 rejected.
- Linting, type checks, tests, and the production build still run on CircleCI for every pull request, so nothing reaches `main` unchecked; this workflow only repeats the build for the artifact it deploys.

## Alternatives considered

- Vercel. Nicer URLs and preview deployments, at the cost of an outside project. It stays an option: switching is a new host and a base path of empty.
- Deploying from CircleCI with a deploy key. Rejected for the stored secret.

## Consequences

- The README links the Pages URL and states that it runs in replay mode.
- A change of host later means changing `NEXT_PUBLIC_BASE_PATH` and the link, nothing in the code.
