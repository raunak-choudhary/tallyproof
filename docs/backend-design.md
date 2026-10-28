# Backend design

This document describes the repository layout, the events and their schemas, the Kafka topics, the database, and the API. The overall system is described in [architecture.md](architecture.md).

## Repository layout

```
tallyproof/
  backend/
    pyproject.toml            ruff, mypy, pytest, and coverage settings
    requirements.in           direct runtime dependencies
    requirements-dev.in       direct development dependencies
    requirements.txt          pinned with hashes by pip-tools
    requirements-dev.txt      pinned with hashes by pip-tools
    manage.py
    config/                   Django project
      settings/               base, local, test, and ci settings
      env.py                  typed settings loaded from .env
    tallyproof_core/          plain Python, no Django
      canonical.py            RFC 8785 serialization
      hashing.py              leaf and node hashing with domain separation
      merkle/                 log, inclusion proofs, consistency proofs
      checkpoint.py           C2SP signed checkpoints, Ed25519
      bloom.py                Bloom filter and its sizing math
      ids.py                  prefixed public IDs
      money.py                Decimal money
    tallyproof_pipeline/      Spark jobs, also free of Django
      acquire/                downloads with a source manifest
      bronze_to_silver/       typing, cleaning, personal data removal, quarantine
      quality/                Deequ constraints and metrics history
      gold/                   conformed events and the anomaly overlay
      replay/                 Kafka producer for gold events
      live/                   Treasury daily statement connector
    apps/                     Django apps
      events/                 event schemas, JSON Schema export, topic registry
      ingestion/              consumer loop, validation, deduplication, dead letters
      ledger/                 event store, Merkle log, checkpoints, proofs, outbox, journal
      reconciliation/         matching rules and breaks
      analyst/                query compiler, retrieval, composer, verifier, LLM client
      evals/                  question sets, oracle, runner, metrics
      realtime/               WebSocket fan-out
      health/                 /healthz and /readyz
    tests/                    unit, module, integration, and end-to-end tests
  frontend/                   Next.js app
  infra/                      compose file, database role script, topic setup
  testdata/                   shared cross-language vectors and the CI data sample
  docs/
  .circleci/
  Makefile
```

`tallyproof_core` and `tallyproof_pipeline` are kept free of Django on purpose. The hashing and Merkle code is what a careful reader will scrutinize most, and in plain Python it's easier to read, to test with property-based tests, and to mirror in TypeScript. The Spark jobs don't need a web framework either.

Downloaded data lives in `data/`, which git ignores. Every app has its own README covering what it does, its public interface, and the events it consumes and produces.

## Public IDs

Public IDs look like `<prefix>_<ULID>`: sortable and safe in URLs. Internal integer keys never leave the service.

| Prefix | Entity |
|---|---|
| `evt_` | Ledger event |
| `bat_` | Merkle batch, closed by a checkpoint |
| `src_` | Registered source file (a downloaded archive and its hash) |
| `brk_` | Reconciliation break |
| `doc_` | Policy document version |
| `qry_` | Submitted question |
| `ans_` | Answer |
| `clm_` | Claim within an answer |
| `run_` | Evaluation run |

Business identifiers from the source data, such as award keys and recipient UEIs, are kept as they are inside the event payload. A UEI identifies a registered business entity. Awards to individual people are removed during cleaning, so no personal identifier reaches the ledger.

## Events

### Envelope

```text
EventEnvelope
  event_id          evt_...   unique per emission; a re-delivered duplicate gets a new one
  idempotency_key   str       the logical identity of the event; duplicates share it
  event_type        enum      see the table below
  schema_version    int       starts at 1
  occurred_at       datetime  when it happened (UTC, RFC 3339)
  emitted_at        datetime  when it was produced; a large gap marks a late arrival
  account_id        str       the recipient UEI, or a Treasury account for cash events
  correlation_id    str       traces one event from ingestion to the answer that cites it
  payload           one schema per event type
```

| Event type | Source | Key payload fields |
|---|---|---|
| `obligation.recorded` | USAspending contract transaction with a positive amount | award key, PIID, awarding and funding agency, amount, action date, action type, NAICS and PSC codes, description |
| `obligation.adjusted` | Modification, including de-obligations (negative amounts) | award key, modification number, amount, reason |
| `outlay.reported` | Account-level award financial data | award key, Treasury account, fiscal period, cumulative outlay, period outlay (derived) |
| `cash.movement` | Treasury Daily Treasury Statement | record date, account, deposit or withdrawal, category, amount and its unit |
| `source.registered` | The acquisition step | file name, URL, size, SHA-256, fetch time |

Outlays in the source are cumulative from the start of the fiscal year. The cleaning step derives each period's outlay as the difference from the previous period for the same award and account, and quarantines rows where that goes negative without a matching correction.

Event schemas are Pydantic models exported as JSON Schema draft-07 with internal references only, so they work in both Redpanda's Schema Registry and AWS Glue Schema Registry. Schemas are registered with backward compatibility enforced.

### What gets hashed

The hashed leaf document contains exactly these fields: `event_id`, `idempotency_key`, `event_type`, `schema_version`, `occurred_at`, `emitted_at`, `account_id`, and `payload`. Tracing fields and Kafka coordinates are left out so they can never change a proof.

Three validation rules keep Python and the browser producing identical bytes. Events that break them go to the dead-letter topic.

- The only JSON numbers allowed are integers from 0 up to 2^53. Money, rates, and quantities are decimal strings.
- Every string must be valid Unicode with no lone surrogates. The injected prompt-injection cases deliberately include zero-width and right-to-left characters, and they're part of the shared test vectors.
- IDs are minted from an injectable clock and a seeded random generator, so a seed reproduces the same IDs.

### Labels stay out of events

Anomaly labels are written to a separate manifest keyed by `event_id`, and only the evaluation harness reads it. If labels were in the events, the analyst could read the answer key and evaluation would mean nothing.

## Anomaly catalog

Injected anomalies are seeded and deterministic. Anomalies that occur naturally in the government data are found by documented rules and reported separately, so the two are never mixed.

| Label | What's injected | Caught by | Expected result |
|---|---|---|---|
| `duplicate_delivery` | The same event re-sent | Ingestion deduplication | Rejected and logged |
| `duplicate_award_semantic` | Same recipient, amount, and date under a different award number | Reconciliation | `possible_duplicate_award` break |
| `outlay_exceeds_obligation` | Outlays pushed above the award's total obligations | Reconciliation | `outlay_exceeds_obligation` break |
| `orphan_outlay` | An outlay for an award that was never obligated | Reconciliation | `orphan_outlay` break |
| `deobligation_exceeds_award` | A de-obligation larger than the amount obligated | Reconciliation | `deobligation_exceeds_award` break |
| `late_arrival` | An event emitted long after it occurred, possibly after its period closed | Reconciliation watermark | `late_after_close` break, posted to the open period |
| `injection_description` | Instructions aimed at the LLM inside a description field | Analyst defenses | Answer unaffected; measured in evaluation |
| `schema_invalid` | A malformed event | Ingestion validation | Dead-letter topic |
| `recipient_burst` | Eight new small awards to one recipient, five minutes apart, each with a different amount | Heavy-hitter detection (later) | Flagged |

Injected outlays borrow a Treasury account from a real outlay in the stream when there is one. Every label is injected in each build; the scenario (`DATA_SCENARIO`) sets how many of each and how many real events surround them.

Periods are fiscal months. A period closes when the watermark, the latest event time seen minus `RECON_LATE_ARRIVAL_WATERMARK_HOURS`, passes its end. Late events post to the open period with a reference to the closed one; closed periods are never edited.

## Kafka topics

Topics are named `<domain>.<entity>.<stage>.v<major>`.

| Topic | Key | Local partitions | Retention | Producer | Consumers |
|---|---|---|---|---|---|
| `fin.events.raw.v1` | `account_id` | 6 | 7 days | replay producer, live connector | ingestion |
| `fin.events.dlq.v1` | `account_id` | 1 | 30 days | ingestion | replay tool |
| `ledger.appended.v1` | `account_id` | 6 | 7 days | outbox relay | reconciliation, journal, lake sink, realtime |
| `ledger.checkpoints.v1` | log origin | 1 | compacted | checkpointer | realtime, witness export |
| `recon.breaks.v1` | `account_id` | 3 | 7 days | reconciliation | realtime |

Events are keyed by recipient because reconciliation works per award and recipient, so ordering matters there. Duplicates share a key, which puts them on the same partition, where the per-partition Bloom filter can see both. A recipient with a very large share of events can skew partitions. The load test reports partition balance.

## Database

PostgreSQL 16 with pgvector.

```mermaid
erDiagram
  LEDGER_EVENT ||--o{ JOURNAL_LINE : "derives"
  LEDGER_EVENT }o--|| LEDGER_BATCH : "sealed by"
  RECON_BREAK ||--o{ BREAK_EVENT : "lists"
  LEDGER_EVENT ||--o{ BREAK_EVENT : "involved in"
  ANSWER ||--o{ CLAIM : "contains"
  CLAIM ||--o{ CITATION : "cites"
  CITATION }o--o| LEDGER_EVENT : "event"
  CITATION }o--o| POLICY_DOCUMENT : "document"
  EVAL_RUN ||--o{ EVAL_RESULT : "has"
  LEDGER_EVENT {
    bigint id PK
    text public_id UK
    bigint leaf_index UK
    text idempotency_key UK
    text event_type
    text account_id
    timestamptz occurred_at
    timestamptz ingested_at
    bytea canonical_bytes "source of truth"
    bytea leaf_hash
    jsonb payload "generated from canonical_bytes"
    text kafka_topic
    int kafka_partition
    bigint kafka_offset
    text correlation_id
  }
  LEDGER_BATCH {
    bigint id PK
    text public_id UK
    bigint start_index
    bigint tree_size
    bytea root_hash
    text checkpoint_body
    bytea signature
    text key_id
    timestamptz closed_at
  }
  JOURNAL_LINE {
    bigint id PK
    bigint event_id FK
    text entry_id
    text account_code
    numeric debit
    numeric credit
  }
  RECON_BREAK {
    bigint id PK
    text public_id UK
    text break_type
    numeric amount_delta
    timestamptz detected_at
  }
  POLICY_DOCUMENT {
    bigint id PK
    text public_id UK
    int version
    bigint leaf_index UK
  }
  ANSWER {
    bigint id PK
    text public_id UK
    text question
    text status
    text refusal_reason
  }
  CLAIM {
    bigint id PK
    text public_id UK
    text kind
    jsonb query_spec
    jsonb bound_values
  }
  CITATION {
    bigint id PK
    bigint leaf_index
  }
  EVAL_RUN {
    bigint id PK
    text public_id UK
    jsonb metrics
    text git_sha
  }
  EVAL_RESULT {
    bigint id PK
    text question_id
    jsonb scores
  }
```

Supporting tables: `merkle_log_head` (a single row holding the next leaf index), `consumer_offset`, `dedupe_rejection`, `outbox`, and `doc_chunk` with a 384-dimension embedding column.

Constraints worth knowing about:

- `payload` is a stored generated column computed from `canonical_bytes`. Analyst views read `payload`, so changing what the analyst sees means changing the bytes the proof covers.
- Money is `NUMERIC(19,4)`. A journal line has either a debit or a credit, never both, and a deferred trigger makes every entry balance.
- `idempotency_key` and `leaf_index` are unique, and leaf indexes are contiguous.
- The application role can't update, delete from, or truncate the append-only tables, and triggers reject updates and deletes as a second layer.
- Each schema change is its own migration, reviewed on its own.

The journal uses simplified budgetary accounting: an obligation moves funds from available authority to obligated, an outlay moves them from obligated to disbursed, and a de-obligation reverses the first step. It's derived from events in log order, so it can always be rebuilt ([ADR-0013](adr/0013-double-entry-journal.md)).

### Roles

| Role | Can do |
|---|---|
| `tallyproof_owner` | Owns the schema and runs migrations, through its own connection string |
| `tallyproof_app` | Insert and select on ledger tables; no update, delete, or truncate on append-only tables |
| `tallyproof_analyst` | Select on the `analyst` views only, read-only transactions, tight timeouts |

Roles are created by a script that runs the same way locally and in CI. Grants live in an idempotent migration with default privileges, so tables created later inherit them.

### Analyst views

`analyst.obligations`, `analyst.outlays`, `analyst.awards` (one row per award with totals), `analyst.cash_movements`, `analyst.breaks`, and `analyst.journal`. Every view exposes `event_id`, so each answer can cite the records behind it. Raw bytes, Kafka coordinates, and internal IDs stay hidden, and free-text description columns appear only in a separate view the query compiler must request explicitly.

## API

All endpoints are under `/api/v1/` and return JSON. The OpenAPI schema is at `/api/v1/schema/`, with browsable docs at `/api/v1/docs/`. Errors use RFC 9457 problem details.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/events` | Events, cursor-paginated, filterable by account, type, and date |
| GET | `/api/v1/events/{event_id}` | One event with its canonical bytes and leaf index |
| GET | `/api/v1/events/{event_id}/proof` | Inclusion proof against the latest or a chosen checkpoint |
| GET | `/api/v1/batches` | Batches and their checkpoints |
| GET | `/api/v1/batches/{batch_id}` | One batch with its signed checkpoint |
| GET | `/api/v1/batches/{batch_id}/consistency?from={batch_id}` | Consistency proof between two checkpoints |
| GET | `/api/v1/checkpoints/latest` | The latest signed checkpoint |
| GET | `/api/v1/log-key` | Public key and log origin |
| GET | `/api/v1/sources` | Registered source files with their hashes |
| POST | `/api/v1/queries` | Ask a question. Rate limited |
| GET | `/api/v1/answers/{answer_id}` | An answer with its claims, bound values, and citations |
| GET | `/api/v1/reconciliation/breaks` | Breaks, filterable by type and account |
| GET | `/api/v1/reconciliation/breaks/{break_id}` | One break and the events involved |
| GET | `/api/v1/policy-documents/{document_id}` | A policy document version and its leaf index |
| GET | `/api/v1/eval-runs` | Evaluation runs |
| GET | `/api/v1/eval-runs/{run_id}` | Metrics and per-question results for one run |
| GET | `/healthz` | Liveness, no dependencies |
| GET | `/readyz` | Checks the broker, database, and cache |

Live updates stream over the WebSocket at `/ws/v1/stream`: appended events, checkpoints, and breaks.

A proof response looks like this:

```json
{
  "event_id": "evt_01J...",
  "leaf_index": 4211,
  "canonical_event_b64": "...",
  "audit_path_hex": ["...", "..."],
  "checkpoint": {
    "batch_id": "bat_01J...",
    "origin": "tallyproof.dev/log/v1",
    "tree_size": 5000,
    "root_hash_b64": "...",
    "body": "...",
    "signature_b64": "...",
    "key_id": "rel-..."
  }
}
```

The API returns proofs, never verdicts. There's no `"verified": true` anywhere. The client computes the leaf hash itself and does the checking.

## Commands

Workers run as Django management commands: `run_ingestion`, `run_checkpointer`, `run_outbox_relay`, `run_reconciliation`, `run_lake_sink`, `export_replay_bundle`, `export_witness`, and `tamper`. The last one is a demo tool and refuses to run outside a local setup.

The data pipeline runs through `make`: `data-fetch` downloads archives and records the manifest, `data-build` runs the Spark jobs, and `data-replay` streams gold events into Kafka.
