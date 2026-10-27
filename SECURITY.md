# Security Policy

## Scope

This project uses public U.S. government spending data with personal information removed, plus labeled synthetic anomalies. It contains no customer data and no personal data. Security reports are welcome, especially about:

- Any personal data that survived the cleaning step (please report privately)

- Ways to make a tampered ledger record pass verification
- Escapes from the analyst's SQL guard or read-only database role
- Prompt injection that changes an answer's cited values or citations
- Secret exposure in code, CI configuration, or build artifacts

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting ("Report a vulnerability" under the Security tab) rather than a public issue. Include steps to reproduce and the commit SHA. You can expect an acknowledgement within 7 days.

## Supported versions

Only the latest commit on `main` and the most recent release tag are supported.

## Design references

The threat model is in [`docs/threat-model.md`](docs/threat-model.md).
