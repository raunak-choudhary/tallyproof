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
- Free text is scrubbed too. A contract's description sometimes carries a contracting contact's work email and phone number; the gold step replaces each with a marker, and the event schema refuses any description that still holds one, so the ledger can't carry them whatever the source (`tallyproof_core/contact_data.py`).
- Three tests guard this. One fails the build if any deny-listed column exists in the cleaned schema, one checks that contact details are found and removed in every form they take in the source (and that standards numbers, clause numbers, and account codes are left alone), and one scans every dataset committed to this repository for them.
- A review on 2026-10-29 found two descriptions with contact details in the committed evaluation dataset, before this scrub existed. They were removed, but the commit that added them stays in the repository's history, because history is never rewritten here. The details were a work email and office numbers published by USAspending.
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

*Built: the read-only role with its timeouts and resource limits (`infra/postgres/create-roles.sql`), the curated `security_barrier` views, the query compiler, and the guard (`backend/apps/analyst/sql_guard.py`). An integration test shows the role refuses every write even with read-only mode switched off, and a hostile-SQL corpus covers every guard rule below.*

Most numeric questions never produce free-form SQL. The model fills in a typed query spec, and the server compiles it into SQL it already knows is safe ([ADR-0014](adr/0014-constrained-query-ir.md)). Every compiled query is pinned to the answer's checkpoint, including the award fields (contract number and agency) that the views take from an award's first record and the award totals, which are added up only from leaves before the checkpoint.

The fallback path, which accepts model-written SQL, is off unless `ANALYST_SQL_FALLBACK` is set; questions the spec can't express are refused as `not_expressible`. When it is on, the SQL is treated as hostile input and checked at two layers, and its answers are labelled lower assurance.

At the database:

- A dedicated read-only role that can see only the curated `analyst` views it is granted by name, with `default_transaction_read_only` on and `search_path` pinned. It can't read the view of source descriptions, whose free text may carry planted instructions, or the policy view, and a view added later stays unreadable until a migration grants it.
- `REVOKE ALL ON SCHEMA public FROM PUBLIC`, no access to catalog views beyond what Postgres requires, and `security_barrier` views.
- A 3 second statement timeout, a 1 second lock timeout, a 5 second idle-in-transaction timeout, 16 MB of working memory, a 64 MB temp file limit, and at most 24 connections.

In the query guard, which parses SQL with sqlglot before anything runs:

- Exactly one `SELECT` statement. Anything else is rejected, including set operations and data-modifying CTEs.
- Allowlists for relations, columns, functions, operators, and cast targets. Schema-qualified names, `pg_*` and `information_schema` relations, `WITH RECURSIVE`, nested `WITH`, CTE names that shadow another relation, set-returning functions, `LATERAL`, locking clauses, and casts to `reg*` types are all rejected. The awards view is left out, because its totals ignore the checkpoint.
- A selected value must be a bare view column or a plain aggregate of one, so a query can't put a literal or an expression beside a real event ID and have it cited. When the output carries event IDs, the query reads one view directly, with no join, CTE, or subquery in its FROM, and every output is a bare column under its own name, so a value from another row can't sit beside a cited event and a label can't misname it. Rows without an event ID and leaf index give no evidence.
- Joins need an equality between the same key on two different tables, with no top-level `OR`, so `ON a.k = a.k OR true` doesn't sneak a cartesian product through.
- Every view is pinned to the checkpoint, and so is each award's first record when the query uses an award field.
- Limits on AST depth and node count, plus an injected `LIMIT`.
- The guard executes SQL re-rendered from the parsed tree, never the original string, which closes parser-differential tricks.

Clients only ever see generic error codes, never raw Postgres messages, because error text can leak data. A hostile-SQL corpus covers every rule above, and an integration test shows the role refuses writes even with the guard switched off. Timing side channels are limited by the timeouts and rate limits but not eliminated. That's a documented residual risk.

### Prompt injection

*Built (`backend/apps/analyst/pipeline.py`, `answer.py`): questions, evidence, and policy text go to the model inside delimited data blocks, with the delimiter tags themselves stripped from anything placed inside one; descriptions stay out of the views the model reads; the verifier drops any clause without a bound value or citation and rejects free numbers, unknown citations, and inexact quotes. Policy text enters only through a reviewed pull request (`backend/corpus/far`, covered by CODEOWNERS). The analyst page renders the model's text as plain text through React, never as HTML, and the only links it makes are to the citation anchors on the same page.*

| Threat | Control |
|---|---|
| Instructions hidden in descriptions or policy text | Untrusted text goes into clearly delimited data blocks, length-capped, and the system prompt says data is never instructions |
| The model told to state numbers or cite records it didn't retrieve | Numbers come only from query results through typed slots, or, in a policy answer, from a word-for-word quote of the regulation that the verifier checks against the cited leaf. Citations must reference IDs in the evidence set. The verifier also catches numbers written as words, numerals other than ASCII digits, a value with a digit, sign, or scale word attached, and two values run together. A number from the question is allowed only when the filter shown with the answer contains that same number; whole numbers are compared, so a figure can't be rebuilt from the filter's digit groups. It rejects anything else ([ADR-0009](adr/0009-bound-claims-answer-format.md)) |
| A claim smuggled into an uncited clause | Each clause after a semicolon, or after a sentence that ends and starts again in lowercase, needs its own bound value or citation |
| A value read as another group's | When one sentence mixes values from several citations, each value is shown with its own |
| A made-up quotation | A policy answer must give at least one passage word for word, and text the model puts in quotation marks inside a sentence must appear in a source that sentence cites |
| A verdict dressed up as an answer | Questions asking whether someone committed fraud, bribery, embezzlement, and similar wrongs are refused by rule, even when they mention the regulation, unless they ask what the regulation's text says. A data answer that uses such words is rejected |
| Injected claims with no numbers in them ("approved by the CFO") | Free-text columns are left out of analyst views unless a query asks for them. Each sentence the model writes must carry a bound value or a citation, or it gets dropped |
| A poisoned policy document | Policy text enters the corpus only through a reviewed pull request. There's no upload path at runtime |
| Exfiltration through rendered output | Answers render as plain text plus structured claim components. Model output never becomes links, images, or HTML |
| The model told to change behavior | It has no write tools at all |

Injection resistance is an evaluation category with a CI threshold ([evaluation.md](evaluation.md)).

### Checking a citation in the browser

The Verify button checks more than the proof itself. The record must be the event the answer cited, its proof must be for the cited leaf, and the checkpoint must be the one the answer was pinned to; a valid proof for anything else fails. For a quoted passage, the quoted text must appear in the record's own text. Each check's result belongs to one answer, so a new answer never shows an earlier answer's result.

### Checking a total in the browser

A proven total is checked against a signed Merkle-sum tree root: the note must be signed by the pinned key and be for the answer's checkpoint, the proof must rebuild that root while every join's sums, counts, and key order add up, and the total and count the answer shows must be the ones the proof gives. A record left out of a total, or slipped into one, fails. What the proof can't show is that the signed tree was built honestly from the log. That is checked the way the log is: the tree is a pure function of a checkpoint's records, so anyone with the log can rebuild it and compare roots ([ADR-0024](adr/0024-merkle-sum-tree-for-provable-totals.md)).

### Tampering and signing keys

Tamper detection is layered. The browser recomputes the leaf from the record's bytes, walks the inclusion proof to the root, and checks the checkpoint's signature against a key pinned in the web build. On the record pages the browser also fetches a checkpoint someone else timestamped, from a different origin than the site (`witness/replay/` on raw.githubusercontent.com), and checks a consistency proof from it to the signed root, so a history rewritten with a stolen key fails there; `make verify-witness` and the integration tests run the same check on the live log. The full ladder is in [architecture.md](architecture.md#tamper-detection).

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
- A structlog processor redacts keys, tokens, and passwords in connection strings, once before a line is formatted and again after, so a traceback's text is covered too. It has its own unit tests.
- `LLM_BASE_URL` must use https unless it points at the same machine, and the API refuses to start in debug mode with a real model provider, because debug pages can show the key.

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
- Rate limits apply per client with explicitly configured trusted proxies, and an IPv6 client counts as its whole /64, so rotating addresses doesn't reset them. Questions to the analyst have their own, tighter limit (`API_THROTTLE_ANON_QUERIES`, 10 a minute). The API runs threaded workers, so a question waiting on the model holds one thread rather than a process. Each process answers at most `ANALYST_MAX_INFLIGHT` questions at once and returns a 503 with `Retry-After` past that. Each client may spend `ANALYST_PER_IP_DAILY_TOKENS` model tokens a day, charged after every model call, and no call is made once it's past that. The API waits at most `ANALYST_MAX_RETRY_WAIT_SECONDS` when the provider asks it to retry. A breaker that switches to cached answers is planned before any public deployment; today the analyst runs only locally and in evaluations.
- Filter values are bounded to what their columns hold, so a number like `1e100000000000000` is refused before it's formatted. A grouped answer covers at most 100 groups.
- `/readyz` reuses its result for five seconds, so a flood of requests doesn't open a connection each.
- List endpoints use cursors and cap a page at 200 items, and size parameters are validated. Proofs come from one in-memory tree that's extended as the log grows, so a request never rebuilds the log. A proof of a total needs that checkpoint's sum tree, which takes about 500 MB and a few seconds to build on a million records, so each process keeps only the two most recently used, builds one at a time, and answers a request that would start a second build with a 503 and `Retry-After` instead of queueing it.
- WebSockets check the origin against `DJANGO_ALLOWED_HOSTS`, cap connections per client (`WS_MAX_CONNECTIONS_PER_IP`), counted only once a connection is accepted, and limit frame size (`WS_MAX_MESSAGE_BYTES`). Frames clients send are dropped unread. A slow client drops its own oldest facts instead of slowing anyone else. The stream process serves WebSockets only and answers plain HTTP with 404, and it trusts forwarded client addresses only when proxies are configured.
- Public IDs carry 80 random bits (ULIDs), so they can't be enumerated.
- CORS is limited to the configured web origin, and standard security headers are set: a Content-Security-Policy that allows nothing on JSON responses, HSTS wherever HTTPS is configured, `X-Content-Type-Options`, `Referrer-Policy`, and `X-Frame-Options`.


A public live backend was considered and not built. It would expose the analyst to anyone, spending the free tier's shared daily quota for every visitor, and it would add a server, a database, and a signing key on the internet to defend. It would prove nothing the static site doesn't: every record, checkpoint, witness, and total on the public site is verified in the browser against the pinned key. The rate limits, the in-flight cap, and the per-address budget exist and are tested, so the decision can be revisited.

### The public demo

The demo is a static site with no backend, so its attack surface is the files it serves. A manifest lists the SHA-256 of every bundled file and is signed with the release key, and the browser checks that signature against the fingerprint compiled into the page before it trusts anything else. Deploys are pinned to a git commit shown in the page. The tamper demo edits a copy of the record in the reader's browser; nothing is sent anywhere or changed on the server.

### Supply chain

Python dependencies are pinned with hashes through pip-tools, and frontend dependencies through the lockfile. Container images and CircleCI images are pinned by exact version tag (not yet by digest), and GitHub Actions by commit. Dependabot proposes updates, and `pip-audit` and `pnpm audit` run in CI. The embedding model (`BAAI/bge-small-en-v1.5`, through fastembed) downloads by name on first use and isn't yet pinned to a revision or checked against a hash; it only ranks policy text and never touches a number or a proof.

### LLM cost and where prompts go

*Built: per-request input and output token caps, per-run request and token budgets, client-side pacing, and the response cache (`backend/apps/analyst/llm.py`). The query endpoint has its own rate limit, a cap on questions answered at once, and a daily token budget per client address, charged after every call (`backend/apps/analyst/limits.py`).*

Per-request token caps, run budgets, response caching, and rate limits bound the cost. A run that would pass its budget stops before the call, with a clear error, instead of producing a surprise bill.

The live provider is Groq's free tier running `openai/gpt-oss-120b`, chosen after Gemini's free tier turned out to allow only 20 requests a day per model. Prompts contain only public USAspending records and FAR text, so whatever a provider's terms allow it to do with them, nothing private leaves the system. A deployment that handled private data would use a paid tier whose terms rule out training on customer data, and say so here.

## Accepted residual risks

- A key holder who rewrites history before the next external timestamp can't be detected. The exposure window is `WITNESS_INTERVAL_SECONDS`.
- Locally, there's a single signing key and no hardware security module. Production would use AWS KMS ([aws-reference-architecture.md](aws-reference-architecture.md)).
- Narrative faithfulness is scored by an LLM judge, so it's probabilistic.
- Timing side channels on the fallback SQL path are reduced, not removed. The fallback is off by default, and its answers are labelled lower assurance when it's on.
- The verifier recognizes number words from a fixed list. It leaves out "one", which reads as a pronoun far more often than a count, and unusual spellings of a number could still slip past it.
- The in-flight cap and the daily token budget are counted per process unless Django's cache is shared, such as through Redis.
- A client with more than a /64 of IPv6 space can still spread its requests across networks.
- A text filter the model chooses, such as an agency name, can carry digits, and numbers shown in the filter are allowed in the prose. The filter is shown to the reader beside the answer, so such a number is visible as part of what was asked.
- One person wrote both the anomaly injector and the detectors. Near-miss cases and a held-out question set limit how much that bias can flatter the results ([evaluation.md](evaluation.md)).

## Review record

On 2026-10-29 two independent reviews went over the analyst and the API: one tried to break the analyst's promises from the outside, and one audited the code for vulnerabilities. Both reproduced their findings with probe scripts. They found 22 problems: one critical, eight high, seven medium, and six low. Every one is fixed, each with a test that failed before the fix, and the controls above describe the result. Attempts that failed are covered by the existing tests, among them union queries, comma joins, window functions, `pg_sleep`, dollar quoting, Unicode digits in a draft, and spoofed forwarded addresses.

A second pass the same day, by a separate security reviewer over the merged code (`apps/analyst`, `apps/ledger/api`, and `config`), found three more: numbers rebuilt from the filter's digit groups, values from another row or under another name in fallback SQL, and a crash on a model reply that was valid JSON but not an object. All three are fixed, each with a test that reproduced it first.

This document was signed off against commit `622b5a8` and, after the second pass, against `f91eb77`, the commit tagged `v0.1.0`.
