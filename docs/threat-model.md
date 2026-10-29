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

*Built: the read-only role, its 3 second timeout, the curated `security_barrier` views, the query compiler, and the guard (`backend/apps/analyst/sql_guard.py`). An integration test shows the role refuses every write even with read-only mode switched off, and a hostile-SQL corpus covers every guard rule below. Statement and lock timeouts beyond the 3 second statement limit, and the dedicated connection pool, arrive with the query endpoint.*

Most numeric questions never produce free-form SQL. The model fills in a typed query spec, and the server compiles it into SQL it already knows is safe ([ADR-0014](adr/0014-constrained-query-ir.md)). The fallback path, which does accept model-written SQL, is treated as hostile input and checked at two layers.

At the database:

- A dedicated read-only role that can see only the curated `analyst` views, with `default_transaction_read_only` on and `search_path` pinned.
- `REVOKE ALL ON SCHEMA public FROM PUBLIC`, no access to catalog views beyond what Postgres requires, and `security_barrier` views.
- Statement, lock, and idle-in-transaction timeouts, a temp file limit, and a small dedicated connection pool that caps concurrency.

In the query guard, which parses SQL with sqlglot before anything runs:

- Exactly one `SELECT` statement. Anything else is rejected, including set operations and data-modifying CTEs.
- Allowlists for relations, columns, functions, operators, and cast targets. Schema-qualified names, `pg_*` and `information_schema` relations, `WITH RECURSIVE`, set-returning functions, `LATERAL`, locking clauses, and casts to `reg*` types are all rejected.
- Joins need an equality predicate between allowlisted keys, so `ON true` doesn't sneak a cartesian product through.
- Limits on AST depth and node count, plus an injected `LIMIT`.
- The guard executes SQL re-rendered from the parsed tree, never the original string, which closes parser-differential tricks.

Clients only ever see generic error codes, never raw Postgres messages, because error text can leak data. A hostile-SQL corpus covers every rule above, and an integration test shows the role refuses writes even with the guard switched off. Timing side channels are limited by the timeouts and rate limits but not eliminated. That's a documented residual risk.

### Prompt injection

*Built (`backend/apps/analyst/pipeline.py`, `answer.py`): questions, evidence, and policy text go to the model inside delimited data blocks; descriptions stay out of the views the model reads; the verifier drops any sentence without a bound value or citation and rejects free numbers, unknown citations, and inexact quotes. Policy text enters only through a reviewed pull request (`backend/corpus/far`, covered by CODEOWNERS). The analyst page renders the model's text as plain text through React, never as HTML, and the only links it makes are to the citation anchors on the same page.*

| Threat | Control |
|---|---|
| Instructions hidden in descriptions or policy text | Untrusted text goes into clearly delimited data blocks, length-capped, and the system prompt says data is never instructions |
| The model told to state numbers or cite records it didn't retrieve | Numbers come only from query results through typed slots, or, in a policy answer, from a word-for-word quote of the regulation that the verifier checks against the cited leaf. Citations must reference IDs in the evidence set. The verifier rejects anything else ([ADR-0009](adr/0009-bound-claims-answer-format.md)) |
| Injected claims with no numbers in them ("approved by the CFO") | Free-text columns are left out of analyst views unless a query asks for them. Each sentence the model writes must carry a bound value or a citation, or it gets dropped |
| A poisoned policy document | Policy text enters the corpus only through a reviewed pull request. There's no upload path at runtime |
| Exfiltration through rendered output | Answers render as plain text plus structured claim components. Model output never becomes links, images, or HTML |
| The model told to change behavior | It has no write tools at all |

Injection resistance is an evaluation category with a CI threshold ([evaluation.md](evaluation.md)).

### Tampering and signing keys

Tamper detection is layered. The browser recomputes the leaf from the record's bytes, walks the inclusion proof to the root, and checks the checkpoint's signature against a key pinned in the web build. The consistency proof against a checkpoint someone else timestamped is checked today by `make verify-witness` and the integration tests, not yet in the browser; that step is planned with the site. The full ladder is in [architecture.md](architecture.md#tamper-detection).

Keys come in three classes, so a leak of one doesn't compromise the others:

| Class | Key file | Where it lives | What it signs |
|---|---|---|---|
| Local | `secrets/checkpoint_dev.key` (`make keygen KEY=dev`) | Gitignored, on the developer machine | Local checkpoints |
| Test | none | Generated in memory by each test run and thrown away | Test checkpoints |
| Release | `secrets/checkpoint_rel.key` (`make keygen KEY=rel`) | Offline, on the maintainer's machine, never in CI | Public demo checkpoints and the signed bundle manifest |

Each key's ID is derived from its name and public key, as the C2SP signed-note format specifies, so two keys can't be confused.

- Keys load from a file path, not an environment variable, so they never show up in `docker inspect`, debug pages, or crash dumps.
- Only the checkpointer process mounts a private key. The API and analyst never have one.
- Planned: rotation through a key-transition record signed by the old key, with revoked key IDs published alongside the witness data. Today a new key means a new pinned key in the web build.
- Private keys are never committed, test keys included. Tests generate keys at runtime, and a custom gitleaks rule catches the key file format.

Witnesses:

- Checkpoint hashes are timestamped through OpenTimestamps (anchored in Bitcoin, no account needed), at least once every `WITNESS_INTERVAL_SECONDS`. This is the only witness the operator can't forge. An RFC 3161 timestamp authority could be added as a second one; it isn't built.
- The public demo's checkpoints are committed with its signed bundle under `frontend/public/replay/`, covered by CODEOWNERS. That copy is convenient but not independent, since the maintainer controls the repository. Locally, `make verify-witness` fails if the exported witness history no longer matches the log.
- `WITNESS_INTERVAL_SECONDS` sets the longest gap before a checkpoint is timestamped, which is also how long a key thief could act unnoticed.

The append-only tables have no update or delete grants for the application role, triggers as a second layer, and `TRUNCATE` revoked. The local tamper tool used for demos refuses to run unless tampering is explicitly enabled (`DEMO_TAMPER_ENABLED=true`) and the database is on loopback.

### Secrets and configuration

- One typed settings module loads from `.env`, and a missing required variable stops startup with its name. Each process validates only the secrets it actually uses.
- `.env` is ignored by git. `.env.example` lists every variable with an explanation ([configuration.md](configuration.md)).
- gitleaks runs in pre-commit and in CI.
- Nothing environment-specific is hardcoded: model IDs, URLs, thresholds, batch sizes. `scripts/ci/check_literals.py` runs in `make lint` and fails on URL, local-address, and model-ID literals outside the settings modules, docstrings, comments, and tests.
- A structlog processor redacts keys, tokens, and passwords in connection strings, and it has its own unit test.

### CI

*One secret context exists: `llm-eval`, holding the model provider's key, restricted to the `main` branch and used only by the weekly scheduled job. There is no bot token and no CI signing key.*

- Pull request pipelines never get the model key. Their evaluation replays responses recorded in `testdata/llm_cache`; any question without a recording falls back to a scripted client and the whole run is labeled a harness check, held to the integrity gate only.
- Recordings are written only by a deliberate local run with a key and committed like any other change, so they go through review. CI never writes them.
- Passing secrets to forked pull requests is off.
- The README results table is rendered from a fixed schema of numbers and model IDs (`backend/evals/readme_table.py`), which refuses harness checks. No model-written text reaches it.
- CODEOWNERS covers CI configuration, the Makefile, the demo bundle, the policy corpus, the evaluation thresholds and question sets, the recorded model responses, and the ADRs.
- Planned with the weekly results pull request: a fine-grained token, scoped to this repository's contents and pull requests, that can open a pull request but never push to `main`.

### Public endpoints

- Every endpoint is public by design, since all served data is public and free of personal data. The API refuses to start unless `DATA_CLASSIFICATION` is `public-no-pii`.
- Rate limits apply per IP with explicitly configured trusted proxies. Questions to the analyst have their own, tighter limit (`API_THROTTLE_ANON_QUERIES`, 10 a minute). Each process answers at most `ANALYST_MAX_INFLIGHT` questions at once and returns a 503 with `Retry-After` past that, and each client address may spend `ANALYST_PER_IP_DAILY_TOKENS` model tokens a day before its questions are refused without a model call. A breaker that switches to cached answers is planned before any public deployment; today the analyst runs only locally and in evaluations.
- List endpoints use cursors and cap a page at 200 items, and size parameters are validated. Proofs come from one in-memory tree that's extended as the log grows, so a request never rebuilds the log.
- WebSockets check the origin against `DJANGO_ALLOWED_HOSTS`, cap connections per IP (`WS_MAX_CONNECTIONS_PER_IP`), and limit frame size (`WS_MAX_MESSAGE_BYTES`). A slow client drops its own oldest facts instead of slowing anyone else.
- Public IDs carry 80 random bits (ULIDs), so they can't be enumerated.
- CORS is limited to the configured web origin, and standard security headers are set: a Content-Security-Policy that allows nothing on JSON responses, HSTS wherever HTTPS is configured, `X-Content-Type-Options`, `Referrer-Policy`, and `X-Frame-Options`.

### The public demo

The demo is a static site with no backend, so its attack surface is the files it serves. A manifest lists the SHA-256 of every bundled file and is signed with the release key, and the browser checks that signature against the fingerprint compiled into the page before it trusts anything else. Deploys are pinned to a git commit shown in the page. The tamper demo edits a copy of the record in the reader's browser; nothing is sent anywhere or changed on the server.

### Supply chain

Python dependencies are pinned with hashes through pip-tools, and frontend dependencies through the lockfile. Container images and CircleCI images are pinned by exact version tag (not yet by digest), and GitHub Actions by commit. Dependabot proposes updates, and `pip-audit` and `pnpm audit` run in CI. The embedding model (`BAAI/bge-small-en-v1.5`, through fastembed) downloads by name on first use and isn't yet pinned to a revision or checked against a hash; it only ranks policy text and never touches a number or a proof.

### LLM cost and where prompts go

*Partly built: per-request token caps, per-run request and token budgets, client-side pacing, and the response cache exist (`backend/apps/analyst/llm.py`). The query endpoint has its own rate limit, a cap on questions answered at once, and a daily token budget per client address (`backend/apps/analyst/limits.py`).*

Per-request token caps, run budgets, response caching, and rate limits bound the cost. A run that would pass its budget stops before the call, with a clear error, instead of producing a surprise bill.

The live provider is Groq's free tier running `openai/gpt-oss-120b`, chosen after Gemini's free tier turned out to allow only 20 requests a day per model. Prompts contain only public USAspending records and FAR text, so whatever a provider's terms allow it to do with them, nothing private leaves the system. A deployment that handled private data would use a paid tier whose terms rule out training on customer data, and say so here.

## Accepted residual risks

- A key holder who rewrites history before the next external timestamp can't be detected. The exposure window is `WITNESS_INTERVAL_SECONDS`.
- Locally, there's a single signing key and no hardware security module. Production would use AWS KMS ([aws-reference-architecture.md](aws-reference-architecture.md)).
- Narrative faithfulness is scored by an LLM judge, so it's probabilistic.
- Timing side channels on the fallback SQL path are reduced, not removed.
- One person wrote both the anomaly injector and the detectors. Near-miss cases and a held-out question set limit how much that bias can flatter the results ([evaluation.md](evaluation.md)).
