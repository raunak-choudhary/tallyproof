# Security Policy

Tallyproof exists to make tampering detectable, so reports about anything that defeats that are welcome and taken seriously.

## What is in scope

The project uses public U.S. government spending data with personal information removed, plus labeled synthetic anomalies. It holds no customer data and no personal data, and the repository holds no secrets. Reports are especially welcome about:

- A way to make a tampered ledger record pass verification, in the browser or from the command line
- An escape from the analyst's SQL guard or its read-only database role
- Prompt injection that changes an answer's cited values or citations
- Personal data that survived the cleaning step (please report privately)
- Secret exposure in code, CI configuration, build artifacts or the published site

## How to report

Use GitHub's private vulnerability reporting: open the repository's Security tab and choose "Report a vulnerability". Please do not open a public issue for a security problem. Include steps to reproduce and the commit SHA you tested against. You can expect an acknowledgement within 7 days.

## Supported versions

The latest commit on `main` and the most recent release tag are supported. The project is complete at version 1.1.0; security fixes will still be made.

## What is already in place

- Secrets live only in `.env`, which git ignores; a secret scanner runs before every commit and over the branch history in CI, and GitHub's push protection is on.
- The browser trusts one public key compiled into the page and a checkpoint an outside witness timestamped, fetched from a second origin. The [verification trust model](docs/adr/0015-verification-trust-model.md) states exactly what the green check proves.
- The analyst never types a number, runs only a constrained query against a read-only role, and refuses questions it cannot express. The [threat model](docs/threat-model.md) lists every control, the attacks considered, and the residual risks.
- Dependencies are pinned and audited on every pull request.
