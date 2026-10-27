# 11. Security and Threat Model

> Status: Draft for MC-01. Covers REQ-SEC-01 to REQ-SEC-11. Method: STRIDE per trust boundary, plus the tamper ladder in `07-architecture.md` section 7.

## 1. Assets

| Asset | Why it matters |
|---|---|
| Ledger integrity (events, leaves, checkpoints) | The entire thesis |
| Checkpoint signing key (Ed25519 private key) | Whoever holds it can sign a rewritten history |
| Witnessed checkpoints | Last line of defense against level 3 tampering (stolen signing key) |
| Anthropic API key | Cost exposure |
| CircleCI context secrets, GitHub token | Supply chain |
| Analyst database role | Data exfiltration or denial of service via SQL |
| Eval integrity (manifest, thresholds) | Fake quality claims would undermine the project |

All data is synthetic (REQ-SEC-09). The generator uses obviously fake names from a fixed word list, never Faker locales that could produce real-looking personal data, and never real company names.

## 2. Trust boundaries

1. Browser to API (public, untrusted).
2. API to LLM provider (data leaves the system; model output returns untrusted).
3. Event data to LLM prompt (event memos and documents are untrusted content).
4. LLM output to SQL engine (untrusted SQL).
5. App to database (role separation).
6. CI to GitHub and secrets.
7. Ledger to witness (external anchoring).

## 3. Threats and mitigations

### 3.1 SQL agent (REQ-SEC-07)

| Threat | Mitigation (defense in depth) |
|---|---|
| Write or DDL statements | sqlglot AST parse; reject anything that is not a single `SELECT` (including `WITH` containing data-modifying CTEs); role has no write grants; `default_transaction_read_only = on` |
| Reading sensitive tables | Role can only see schema `analyst` views; AST allowlist of relations and columns |
| Dangerous functions (`pg_sleep`, `pg_read_file`, `dblink`, `lo_*`, `set_config`, `current_setting`) | Function allowlist (aggregates, date and numeric functions only) |
| Resource exhaustion | `statement_timeout`, `work_mem`, enforced `LIMIT` injection, row cap on fetch, cartesian join detection (reject joins without a join predicate) |
| Multiple statements / comment tricks | Parse must yield exactly one statement; comments stripped before execution |
| Guard bypass via parser differential | The guard re-renders SQL from the AST and executes the rendered text, never the original string |

Tests: a corpus of malicious SQL strings (unit tests) plus Hypothesis-generated statement mixes, and an integration test proving the role itself refuses writes even if the guard is disabled.

### 3.2 Prompt injection (REQ-SEC-08)

| Threat | Mitigation |
|---|---|
| Instructions inside event memos or policy documents | Untrusted data is placed only in clearly delimited data blocks; the system prompt states that data blocks are never instructions |
| Model told to emit numbers or cite events not in evidence | Bound-slot answer format: numbers can only come from query results; citations can only reference IDs present in the evidence set; verifier rejects anything else |
| Model told to call tools or change behavior | The model has no write tools. The only "tool" is producing SQL, which goes through the guard |
| Exfiltration via answer text (for example, rendering a URL) | Frontend renders answer text as plain text plus structured claim components; no Markdown links or images from model output |
| Indirect injection through the question | Same delimiting; the router uses rules first and a small model second |

Measured by eval category `injection` (anomaly `injection_memo`).

### 3.3 Tampering
See the tamper ladder. Additional controls:
- Append-only grants plus triggers.
- Signing key loaded from `.env`, never logged, never returned by any endpoint; public key published at `/api/v1/log-key` and in the repo.
- Key rotation: checkpoints carry a `key_id`; old public keys stay published.
- Witness export is committed through the normal PR flow, so GitHub history acts as an independent timestamped witness.

### 3.4 Secrets (REQ-SEC-01 to 06)
- One typed settings module (`config/env.py`, pydantic-settings). Missing required variables fail fast with the variable name and a pointer to `13-configuration.md`.
- `.env` is gitignored; `.env.example` lists every variable with a comment (REQ-SEC-03).
- gitleaks in pre-commit and in CI (REQ-SEC-04).
- CI secrets only in a CircleCI context restricted to the `main` branch and to scheduled pipelines; fork PRs get no secrets (REQ-SEC-05).
- Model IDs, thresholds, URLs, batch sizes: all configuration, never literals in code (REQ-SEC-01). A ruff/grep CI check flags string literals matching `claude-` and `http://localhost` outside settings and tests.

### 3.5 Public endpoints (REQ-SEC-10)
- DRF throttling: anonymous rate limits per IP for `POST /api/v1/queries` (strict) and read endpoints (lenient). Backed by Redis.
- Input validation: question length cap, Unicode normalization, rejection of control characters; pagination caps; ID format validation by prefix regex before any database access.
- CORS restricted to the configured web origin; security headers (CSP, HSTS in non-local, `X-Content-Type-Options`, `Referrer-Policy`).
- Public replay demo has no backend, so its attack surface is static files only.

### 3.6 Supply chain
- Pinned Python dependencies (pip-tools with hashes) and npm lockfile (REQ-ENV-02, REQ-ENV-03).
- Dependabot for pip, npm, Docker, CircleCI orbs (REQ-GIT-09).
- Docker images pinned by tag and digest in `compose.yaml`.
- `pip-audit` and `npm audit --audit-level=high` in CI (proposed addition).

### 3.7 Denial of wallet (LLM cost)
- Per-request token caps, per-day spend cap (`LLM_DAILY_USD_CAP`), response cache, and rate limiting. Over-cap requests get a typed refusal.

## 4. Residual risks (accepted, documented)

- Level 4 tampering (key holder acting before the next external timestamp) is not detectable; exposure equals `WITNESS_INTERVAL_SECONDS`.
- Single signing key, no HSM locally. AWS mapping uses KMS (see `15-aws-reference-architecture.md`).
- LLM-judge narrative faithfulness is probabilistic.
- The generator could be biased toward anomalies the system already handles; mitigated by adding anomaly types blind (written before the detector) where possible.

## 5. Hardening from plan review (2026-10-26)

A security-lens review of these docs found gaps. Each item below is now a requirement on the task named.

### 5.1 Independent witness (T-114, T-207)
- A git file in our own repo is **not** an independent witness: the owner, CI, and the bot can all write to it. Therefore every checkpoint hash is also timestamped by a third party the operator does not control: **OpenTimestamps** (Bitcoin-anchored, free, no account) and optionally an **RFC 3161** timestamp authority. Proof files are stored next to the checkpoint.
- `witness/` is protected by CODEOWNERS and branch protection (no force push, admins included). `make verify-witness` fails if witness history is not fast-forward (rewrites are detected).
- `WITNESS_INTERVAL_SECONDS` makes the level 4 exposure window explicit and configurable.
- Tamper ladder level 3 is claimed as caught **only** for checkpoints with an external timestamp. README wording follows this.

### 5.2 Key classes and trust anchors (T-109, T-114, E-506)
| Key class | `key_id` prefix | Where it lives | Signs |
|---|---|---|---|
| local | `dev-` | file mount `secrets/checkpoint_dev.key` (gitignored) | local checkpoints |
| ci | `ci-` | CircleCI context `signing-ci` only | integration test checkpoints |
| release | `rel-` | offline, on Raunak's machine, never in CI | replay bundle checkpoints and signed bundle manifest |

- Keys are loaded from a **file path** (`CHECKPOINT_SIGNING_KEY_FILE`), not an environment variable, so they never appear in `docker inspect`, debug pages, or crash dumps.
- Only the checkpointer process mounts the key. The API and analyst processes never have it.
- The browser's trust anchor is the **release public key fingerprint compiled into the web build** and printed in the README, never read from the bundle it verifies. The UI shows the fingerprint.
- Rotation via a signed key-transition record (old key signs new key); revoked key IDs listed in `witness/revoked-keys.json`.
- Custom gitleaks rule for the key file format. Private keys are never committed, test keys included (tests generate keys at runtime).

### 5.3 SQL guard hardening (T-301, T-302)
- Database: `REVOKE ALL ON SCHEMA public FROM PUBLIC`; analyst role `NOINHERIT`, pinned `search_path = analyst`, no access to `pg_catalog` views beyond what Postgres requires, `security_barrier` views, plus `statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`, `temp_file_limit`, and a dedicated small connection pool (caps concurrency).
- AST: allowlists for relations, columns, **functions, operators, and cast targets**; reject schema-qualified names, any `pg_*` or `information_schema` relation, `WITH RECURSIVE`, set-returning functions (`generate_series`, `unnest`), `LATERAL`, locking clauses, casts to `reg*` types, `query_to_xml` and similar; maximum AST depth and node count; joins require an equality predicate between allowlisted keys (`ON true` rejected).
- Errors: clients receive generic error codes only, never raw Postgres messages (closes error-message data leaks). Latency oracles are bounded by timeouts and rate limits; noted as residual.
- Every rule above has an entry in the hostile SQL corpus.

### 5.4 Prompt injection beyond numbers (T-305, T-306, T-308)
- Number-free injected claims ("approved by the CFO") pass a numbers-only verifier. Therefore: free-text fields (`memo`, `reason`) are excluded from analyst views by default and exposed only through an explicit `memo` column the router must request; untrusted strings are length-capped and wrapped as data; model-authored prose is capped in length and each sentence must carry at least one bound slot or citation, otherwise it is dropped.
- Policy documents enter the corpus only through a reviewed PR to `policies/` (signed commits). No runtime upload path exists.
- `injection` eval category is a CI gate with threshold (see `08-eval-spec.md` section 6).

### 5.5 CI secrets (T-103, T-310)
- **PR pipelines never receive the Anthropic key.** On cache miss, PR evals run in `fake` mode and the smoke gate reports `harness-check`; only `main` and scheduled pipelines run `live` (supersedes the earlier fallback wording in `08-eval-spec.md`).
- Separate contexts: `llm-eval` (Anthropic key, spend-capped dedicated workspace key), `bot` (GitHub App or fine-grained token limited to `contents:write` on `bot/*` branches and `pull_requests:write`), `signing-ci`. Contexts restricted to `main` and scheduled triggers via CircleCI security groups. "Pass secrets to forked PRs" verified off at MC-04.
- LLM response cache is written only by `main` and scheduled runs; PR runs may read but not save, so a PR cannot poison nightly results.
- The README eval table is rendered from a fixed schema of numbers and model IDs; no free text from model output.
- CODEOWNERS covers `.circleci/`, `Makefile`, `witness/`, `evals/thresholds.toml`, `policies/`.

### 5.6 Replay bundle integrity (E-506)
- `manifest.json` lists SHA-256 of every bundle file (events, checkpoints, answers, eval results) and is signed by the release key. The browser checks the manifest signature against the compiled-in fingerprint before anything else.
- Static assets served with a strict CSP; Vercel deploys pinned to a git SHA shown in the UI.
- Replay tamper demo is labeled as an in-browser simulation of the attack.

### 5.7 Public endpoints (T-115, T-209, T-307)
- All endpoints are public by design because all data is synthetic. The API refuses to start if `DATA_CLASSIFICATION` is anything other than `synthetic`.
- Trusted proxy configuration explicit (`TRUSTED_PROXY_COUNT`); throttles per IP plus a global in-flight cap on the analyst; per-IP daily token budget; circuit breaker to cached-only answers when the daily cap nears.
- Proof and consistency endpoints cap ranges and pagination depth; results cached by checkpoint.
- WebSocket: origin allowlist, per-IP connection cap, message size limit.
- `ans_` and `qry_` IDs use ULIDs with 80 random bits; answers are not enumerable.

### 5.8 Miscellaneous
- `tamper` command refuses unless settings module is `local`, the database host is loopback, and `DEMO_TAMPER_ENABLED=true`.
- Log redaction processor in structlog (keys, DSNs with passwords, tokens) with a unit test.
- `.cache/` gitignored and never uploaded as an artifact.
- Compose services bound to `127.0.0.1` only; trust boundary 8 added: **anyone who can produce to `fin.events.raw.v1` can append to the ledger.** The ledger proves integrity since ingestion, not source honesty. Producer authentication and event signing are listed as a Nice-to-have.
- Embedding model pinned by Hugging Face revision hash.
- `pip-audit` and `npm audit` promoted from proposed to required in CI. CircleCI orbs pinned to exact versions.
