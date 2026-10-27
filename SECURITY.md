# Security Policy

## Scope

This project uses synthetic data only. It contains no real customer, financial, or personal data. Security reports are still welcome, especially about:

- Ways to make a tampered ledger record pass verification
- Escapes from the analyst's SQL guard or read-only database role
- Prompt injection that changes an answer's cited values or citations
- Secret exposure in code, CI configuration, or build artifacts

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting ("Report a vulnerability" under the Security tab) rather than a public issue. Include steps to reproduce and the commit SHA. You can expect an acknowledgement within 7 days.

## Supported versions

Only the latest commit on `main` and the most recent release tag are supported.

## Design references

The threat model is in [`docs/11-security-and-threat-model.md`](docs/11-security-and-threat-model.md).
