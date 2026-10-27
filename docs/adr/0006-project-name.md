# ADR-0006: Project name

- Status: **Proposed, awaiting Raunak's choice (MC-02).** Repository created on 2026-10-27 under the working name at the owner's request; a rename later is cheap because GitHub redirects renamed repositories, but it must happen before T-101 so package names are right from the start.
- Date: 2026-10-26

## Criteria (brief Section 4)

Hints at what the system does; credible to a finance audience; short; valid as repo name, Python package, npm package, URL slug; no collision with a well-known product on GitHub, PyPI, npm.

## Method

Checked on 2026-10-26: PyPI JSON API (404 = free), npm registry (404 = free), GitHub repository search by name (count and top stars), plus a web search for products.

## Working name is not viable

`ledgerline`: **taken on PyPI and npm**, 367 GitHub repositories with that name. Rejected.

## Candidates checked (abbreviated)

| Name | PyPI | npm | GitHub repos (top stars) | Notes |
|---|---|---|---|---|
| ledgerline | taken | taken | 367 (17) | Rejected |
| proofledger | taken | taken | 20 | Rejected |
| proofline | taken | taken | 195 | Rejected |
| ledgerproof | taken | free | 27 | Rejected (PyPI) |
| clearledger | free | free | 173 (130) | Rejected (active Stellar project) |
| citeproof | free | free | 10 (93) | Rejected (active MCP project) |
| **tallyproof** | free | free | 3 (0) | No product found in web search |
| **glassledger** | free | free | 7 (0) | A small consumer iOS budgeting app uses "GlassLedger" |
| **ledgerwitness** | free | free | 0 | No product found |
| attestledger | free | free | 0 | Clean but clunky |
| veriledger | free | free | 19 (0) | Generic, many student repos |

## Top 3

### 1. `tallyproof` (recommended)
- Meaning: "proof that the numbers tally." In accounting, figures *tally* when they reconcile; *proof* is both the accounting term (a proof of balances) and the cryptographic one. This is the thesis in two syllables.
- 10 characters, one word, valid everywhere (`tallyproof`, `@tallyproof/verify`, `tallyproof.dev`).
- Risk: "Tally" is also Tally Solutions' TallyPrime, a major accounting product in India. "Tally" is a common English word and the compound is unique, but some reviewers may make the association.

### 2. `glassledger`
- Meaning: a glass-box ledger: you can see inside and verify everything. Instantly understandable to non-technical recruiters.
- 11 characters. Clean on PyPI and npm.
- Risk: a small consumer iOS budgeting app uses the name "GlassLedger". Weak collision (different market), but it exists.

### 3. `ledgerwitness`
- Meaning: in transparency logs, a *witness* independently co-signs checkpoints; in law, a witness attests to a record. Precise for engineers who know transparency logs.
- Completely clean on all registries and the web.
- Risk: 13 characters; "witness" needs explanation for recruiters; "Ledger" prefix may evoke the crypto wallet brand.

## Decision

Pending. After approval: rename the GitHub repository, local folder, Python package (`<name>_core`), npm package, docs, and CLAUDE.md in one `refactor` commit.
