# Threat model

This document covers what Tallyproof protects, who it protects it from, and the controls in place. It is organized by trust boundary, and the tamper-detection model it relies on is described in [architecture.md](architecture.md#tamper-detection).

## What we protect

| Asset | Why it matters |
|---|---|
| Ledger integrity: events, leaf hashes, checkpoints | It's the whole point of the project |
| Checkpoint signing keys | Whoever holds one can sign a rewritten history |
| Externally timestamped checkpoints | The last defense if a signing key is stolen |
| LLM API key | Direct cost exposure |
| CI secrets and the GitHub bot token | A way into the build and the repository |
| The analyst's database role | A path to data leaks or denial of service through SQL |
| Evaluation integrity: labels and thresholds | Inflated quality numbers would undermine everything else |

## Personal data

The data is real public U.S. government spending, plus a labeled synthetic anomaly overlay. Public doesn't mean free of personal data, so the cleaning step (the silver layer of the data pipeline) removes it before anything else sees the data:

- It drops columns holding executive names and compensation, contracting officer and point-of-contact names, phone and fax numbers, email addresses, and street address lines. City, state, and country stay, because aggregate analysis needs them.
- It drops rows for awards made to an individual person or sole proprietor, identified from the source's business-type flags.
- Every removal is counted by reason in the published data profile.
- Two tests guard this. One fails the build if any deny-listed column exists in the cleaned schema. The other scans sample values for email and phone patterns.
- Raw downloads stay in an ignored local directory. They're never served, published, or committed.

## Trust boundaries

1. Browser to API. Public and untrusted.
2. API to the LLM provider. Data leaves the system, and what comes back is untrusted.
3. Source data to the LLM prompt. Free-text fields such as award and transaction descriptions are untrusted.
4. LLM output to the database. Any query the model influences is untrusted.
5. Application to database, separated by role.
6. CI to GitHub and its secrets.
7. Ledger to its witnesses outside the database.
8. Producers to Kafka. Anyone who can write to the raw events topic can append to the ledger. The ledger proves a record is unchanged since ingestion; it doesn't prove the source told the truth.

## Threats and controls

### The analyst's database access

Most numeric questions never produce free-form SQL. The model fills in a typed query spec, and the server compiles it into SQL it already knows is safe ([ADR-0014](adr/0014-constrained-query-ir.md)). The fallback path, which does accept model-written SQL, is treated as hostile input and checked at two layers.

At the database:

- A dedicated read-only role that can see only the curated `analyst` views, with `default_transaction_read_only` on and `search_path` pinned.
- `REVOKE ALL ON SCHEMA public FROM PUBLIC`, no access to catalog views beyond what Postgres requires, and `security_barrier` views.
- Statement, lock, and idle-in-transaction timeouts, a temp file limit, and a small dedicated connection pool that caps concurrency.

In the query guard, which parses SQL with sqlglot before anything runs:

- Exactly one `SELECT` statement. Anything else is rejected, including data-modifying CTEs.
- Allowlists for relations, columns, functions, operators, and cast targets. Schema-qualified names, `pg_*` and `information_schema` relations, `WITH RECURSIVE`, set-returning functions, `LATERAL`, locking clauses, and casts to `reg*` types are all rejected.
- Joins need an equality predicate between allowlisted keys, so `ON true` doesn't sneak a cartesian product through.
- Limits on AST depth and node count, plus an injected `LIMIT`.
- The guard executes SQL re-rendered from the parsed tree, never the original string, which closes parser-differential tricks.

Clients only ever see generic error codes, never raw Postgres messages, because error text can leak data. A hostile-SQL corpus covers every rule above, and an integration test shows the role refuses writes even with the guard switched off. Timing side channels are limited by the timeouts and rate limits but not eliminated. That's a documented residual risk.

### Prompt injection

| Threat | Control |
|---|---|
| Instructions hidden in descriptions or policy text | Untrusted text goes into clearly delimited data blocks, length-capped, and the system prompt says data is never instructions |
| The model told to state numbers or cite records it didn't retrieve | Numbers come only from query results through typed slots, and citations must reference IDs in the evidence set. The verifier rejects anything else ([ADR-0009](adr/0009-bound-claims-answer-format.md)) |
| Injected claims with no numbers in them ("approved by the CFO") | Free-text columns are left out of analyst views unless a query asks for them. Each sentence the model writes must carry a bound value or a citation, or it gets dropped |
| A poisoned policy document | Policy text enters the corpus only through a reviewed pull request. There's no upload path at runtime |
| Exfiltration through rendered output | Answers render as plain text plus structured claim components. Model output never becomes links, images, or HTML |
| The model told to change behavior | It has no write tools at all |

Injection resistance is an evaluation category with a CI threshold ([evaluation.md](evaluation.md)).

### Tampering and signing keys

Tamper detection is layered: a client-side leaf recomputation, a signature check against a key pinned in the web build, and a consistency proof against a checkpoint someone else timestamped. The full ladder is in [architecture.md](architecture.md#tamper-detection).

Keys come in three classes, so a leak of one doesn't compromise the others:

| Class | `key_id` prefix | Where it lives | What it signs |
|---|---|---|---|
| Local | `dev-` | A gitignored key file on the developer machine | Local checkpoints |
| CI | `ci-` | A restricted CircleCI context | Integration test checkpoints |
| Release | `rel-` | Offline, on the maintainer's machine, never in CI | Public demo checkpoints and the signed bundle manifest |

- Keys load from a file path, not an environment variable, so they never show up in `docker inspect`, debug pages, or crash dumps.
- Only the checkpointer process mounts a private key. The API and analyst never have one.
- Rotation uses a key-transition record signed by the old key. Revoked key IDs are published with the witness data.
- Private keys are never committed, test keys included. Tests generate keys at runtime, and a custom gitleaks rule catches the key file format.

Witnesses:

- Every checkpoint hash is timestamped through OpenTimestamps (anchored in Bitcoin, no account needed), and optionally through an RFC 3161 timestamp authority. This is the only witness the operator can't forge.
- A copy of the checkpoints also lives in the repository under branch protection and CODEOWNERS. It's convenient, but it isn't independent, since the maintainer controls the repository. Verification fails if that history is ever rewritten.
- `WITNESS_INTERVAL_SECONDS` sets the longest gap before a checkpoint is timestamped, which is also how long a key thief could act unnoticed.

The append-only tables have no update or delete grants for the application role, triggers as a second layer, and `TRUNCATE` revoked. The local tamper tool used for demos refuses to run unless the settings module is `local`, the database is on loopback, and tampering is explicitly enabled.

### Secrets and configuration

- One typed settings module loads from `.env`, and a missing required variable stops startup with its name. Each process validates only the secrets it actually uses.
- `.env` is ignored by git. `.env.example` lists every variable with an explanation ([configuration.md](configuration.md)).
- gitleaks runs in pre-commit and in CI.
- Nothing environment-specific is hardcoded: model IDs, URLs, thresholds, batch sizes. A CI check flags model-ID and localhost literals outside settings and tests.
- A structlog processor redacts keys, tokens, and passwords in connection strings, and it has its own unit test.

### CI

- Pull request pipelines never get the LLM key. When a PR's evaluation hits an uncached prompt, that item runs against a fake client and the run is labeled as a harness check. Only `main` and scheduled pipelines call the real model.
- Secrets sit in three separate CircleCI contexts (LLM evaluation, the GitHub bot, CI signing), each restricted to `main` and scheduled triggers. Passing secrets to forked PRs is off.
- The bot token can only push to `bot/*` branches and open pull requests. It can't push to `main`.
- Only `main` and scheduled runs write to the LLM response cache, so a pull request can't poison nightly results.
- The results table in the README is generated from a fixed schema of numbers and model IDs. No model-written text reaches it.
- CODEOWNERS covers CI configuration, the Makefile, witness data, evaluation thresholds, and policy documents.

### Public endpoints

- Every endpoint is public by design, since all served data is public and free of personal data. The API refuses to start unless `DATA_CLASSIFICATION` is `public-no-pii`.
- Rate limits apply per IP with explicitly configured trusted proxies, alongside a global cap on concurrent analyst requests, a per-IP daily token budget, and a breaker that switches to cached answers when the daily spend cap gets close.
- Proof and consistency endpoints cap their ranges and pagination depth, and results are cached per checkpoint.
- WebSockets check the origin, cap connections per IP, and limit message size.
- Answer and query IDs carry 80 random bits, so they can't be enumerated.
- CORS is limited to the configured web origin, and standard security headers are set (CSP, HSTS outside local, `X-Content-Type-Options`, `Referrer-Policy`).

### The public demo

The demo is a static site with no backend, so its attack surface is the files it serves. A manifest lists the SHA-256 of every bundled file and is signed with the release key, and the browser checks that signature against the fingerprint compiled into the page before it trusts anything else. Deploys are pinned to a git commit shown in the page, and the in-browser tamper demo says plainly that it simulates the attack.

### Supply chain

Python dependencies are pinned with hashes through pip-tools, and frontend dependencies through the lockfile. Container images are pinned by tag and digest, and CircleCI orbs by exact version. Dependabot proposes updates, and `pip-audit` and `npm audit` run in CI. The embedding model is pinned to a specific revision.

### LLM cost

Per-request token caps, a daily spend cap, response caching, and rate limits bound the cost. Requests over the cap get a typed refusal instead of a surprise bill.

## Accepted residual risks

- A key holder who rewrites history before the next external timestamp can't be detected. The exposure window is `WITNESS_INTERVAL_SECONDS`.
- Locally, there's a single signing key and no hardware security module. Production would use AWS KMS ([aws-reference-architecture.md](aws-reference-architecture.md)).
- Narrative faithfulness is scored by an LLM judge, so it's probabilistic.
- Timing side channels on the fallback SQL path are reduced, not removed.
- One person wrote both the anomaly injector and the detectors. Near-miss cases and a held-out question set limit how much that bias can flatter the results ([evaluation.md](evaluation.md)).
