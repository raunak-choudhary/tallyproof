# analyst

Answers questions about the ledger with numbers bound to query results and citations the browser can verify. It's being built in stages.

| Module | What it does |
|---|---|
| `migrations/` | The curated `analyst` views: obligations, outlays, awards, cash movements, breaks, journal, and policy sections. Descriptions are a separate view because they're untrusted source text |
| `query_spec.py` | The query spec the model fills in instead of writing SQL, and the catalog of entities and fields it may name ([ADR-0014](../../../docs/adr/0014-constrained-query-ir.md)) |
| `sql_guard.py` | Decides whether model-written SQL on the fallback path may run: one SELECT, allowlisted views, columns, functions, casts, and joins, an injected limit, and SQL rebuilt from the parsed tree |
| `llm.py` | The model client interface and its implementations: a scripted fake, a client for any OpenAI-compatible provider (Groq's `gpt-oss-120b` live), a response cache keyed by model, prompt version, and parameters, and per-run budgets |
| `router.py` | Routes a question: fixed rules for refusals, policy questions, and known anomaly lists; the model, answering in JSON, for the rest. Its spec is validated before use |
| `retrieval.py` | Finds the FAR text a question is about: chunks of each section's leaf, BM25 and local embeddings fused by reciprocal rank. Each chunk keeps its leaf and offsets, so quotes cite and check against the exact leaf |
| `answer.py` | Bound-claim answers (ADR-0009): evidence as typed slots, citations, and quote sources; the verifier that rejects free numbers, unbound labels, and inexact quotes; rendering |
| `pipeline.py` | Question to answer: route, compile and run (or guarded fallback SQL, or policy retrieval), compose, verify, one repair, otherwise a typed refusal |
| `service.py` | Wires the pipeline to the analyst connection, the configured model, and the FAR index; answers as of the newest checkpoint and stores the result |
| `api.py` | `POST /api/v1/queries` (own rate limit) and `GET /api/v1/answers/{answer_id}`; every cited event comes with its proof URL, never a verdict |
| `models.py` | `analyst_answer`, append-only |
| `compiler.py` | Compiles a spec into SQL over the views, pinned to a checkpoint, with every value bound and the filter rendered in words |

The `tallyproof_analyst` role can read these views and nothing else. Its connections are read-only by default, time out after 3 seconds, and have `search_path` pinned to `analyst` (`infra/postgres/create-roles.sql`). Even with read-only mode switched off, it holds no grant that allows a write.

Settings: `LLM_*` ([configuration](../../../docs/configuration.md)).

Tests: `tests/unit/analyst/`, `tests/integration/analyst/`.
