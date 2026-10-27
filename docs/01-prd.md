# 01. Product Requirements Document

> Working name: **Ledgerline** (final name pending MC-02, see `adr/0006-project-name.md`).
> Status: Draft for MC-01 approval. Owner: Raunak Choudhary. Last updated: 2026-10-26.

## 1. Problem

AI assistants are entering finance workflows (close, reconciliation, AP/AR analysis, audit support). They fail in three ways that matter more in finance than anywhere else:

1. **Wrong numbers.** LLMs produce plausible but incorrect figures, especially for aggregates.
2. **Unfaithful citations.** Models cite sources they did not actually use, or sources that do not support the claim.
3. **Unverifiable sources.** Even a faithful citation points at a database row that could have been edited after the fact. Nobody can prove the cited record is what was originally recorded.

Regulators now treat this as a governance problem (see `README.md`, "Why this exists", for the verified source list). Separately, AWS retired Amazon QLDB in 2025 and points customers to Aurora PostgreSQL, which does not ship an immutable, cryptographically verifiable change history. Teams have to build that history themselves.

## 2. Product thesis

> An AI analyst is only as trustworthy as the weakest link between its sentence and the original record. Ledgerline makes every link checkable by the reader, not by the server.

The chain:

```
source event --(Kafka)--> ingestion --(canonical bytes, SHA-256 leaf)--> append-only ledger
   --> Merkle log --> signed checkpoint --> published outside the database (witness)
answer sentence --> claim --> bound value + cited event IDs --> inclusion proof --> checkpoint
```

The browser verifies the chain trusting only a pinned public key and an externally timestamped checkpoint (ADR-0015).

## 3. Users and audiences

| Audience | What they need in under 2 minutes | What they need in 20 minutes |
|---|---|---|
| Recruiter / hiring manager (primary for the public link) | Understand the idea from the landing animation; see the tamper demo fail a citation | README, eval table, architecture diagram |
| Finance data-platform engineer (primary technical reviewer) | Kafka topic design, exactly-once story, partitioning, control totals, AWS mapping | Code quality of ingestion and ledger, tests, CI, honest scale report |
| Applied AI engineer | How citations are bound, refusal policy, eval methodology | Eval spec, golden set generation, baseline comparison |
| Security-minded reviewer | Threat model, SQL guardrails, prompt-injection defenses | Tamper ladder, key handling, read-only role |
| Hackathon judge | Wow moment, clarity, working demo | Novelty versus prior art (answerproof) |

Persona used for in-product flows: **Maya, an AP/AR analyst** at a mid-size company who asks "Which customer payments this month have no matching invoice, and how much do they total?" and must be able to defend the answer to an auditor.

## 4. Goals and non-goals

### Goals
- G1. Every numeric value in an answer comes from an executed query, never from model text.
- G2. Every claim cites at least one source event (or policy document) with an inclusion proof that a browser can verify against a signed checkpoint.
- G3. Unverifiable claims are refused, and refusal correctness is measured.
- G4. Answer quality is measured against **exact** ground truth produced by the generator, and CI fails on regression.
- G5. The pipeline demonstrates real streaming engineering: partitioning, consumer groups, idempotent effectively-once processing, DLQ, outbox, control totals, a lake sink, and a measured load test.
- G6. A public demo that never sleeps, needs no backend, and still verifies real proofs.

### Non-goals
- Real customer data, real PII, real money movement (REQ-SEC-09).
- Multi-tenant SaaS, authentication flows, billing.
- Being a general-purpose accounting system. Double-entry is used to make the ledger credible and queryable, not to replace an ERP.
- Zero-knowledge proofs (future work, cited as VeriRAG if verified).
- Claims of scale beyond what the load test measured.

## 5. Scope tiers

Tiers follow the brief (Section 13). Changes from the brief are marked **(changed)** and justified in `12-risks-and-decisions-log.md`.

### MVP (target `v0.1.0`)
- Seeded generator with labeled anomaly catalog; labels written to a separate ground-truth manifest.
- Redpanda ingestion: schema validation, DLQ, Bloom fast path plus UNIQUE constraint dedupe, offsets committed in the same Postgres transaction as ledger writes.
- Append-only ledger enforced by database grants and triggers.
- Merkle log (RFC 9162 hashing) with size-or-time batches, Ed25519-signed checkpoints, inclusion and consistency proofs, proof API.
- **(changed)** Checkpoints exported to a witness file committed to the repo and to the replay bundle (external anchoring). Moved up from implicit to MVP because without it the tamper story has a hole.
- Reconciliation engine producing typed breaks.
- **(changed)** Double-entry journal derived from events (small, deterministic). Added because a finance reviewer expects debits to equal credits.
- Analyst: router, guarded text-to-SQL over curated views, policy retrieval, bound-claim answer format, verifier, refusal.
- Eval harness, golden set, smoke eval gate in CI.
- Basic UI: event page with Verify, analyst page, tamper action.
- CI green on CircleCI.

### MLP (target `v0.2.0` to `v0.9.x`)
- Motion landing page, live stream dashboard, citation proof visualization, polished tamper ladder demo, eval dashboard, replay-mode public demo on Vercel, README hero diagram and GIF.
- **(changed)** Parquet lake sink plus control totals moved from Nice-to-have to MLP. Reason: it is the single strongest signal for a data-pipeline team, and it is cheap once the outbox exists.
- **(changed)** Measured load-test report moved from Nice-to-have to MLP. Reason: honest numbers are required by Section 14 anyway.
- Baseline comparison eval: naive RAG versus Ledgerline on the same golden set.

### Nice-to-have (target `v1.0.0` if CI is green)
- Count-Min Sketch heavy hitters (suspicious vendor patterns).
- Schema evolution demo with registry compatibility checks (event v1 to v2).
- DuckDB batch reconciliation over the lake at 10M+ rows.
- Merkle-sum tree for provable totals (closes the completeness gap, see `07-architecture.md` section 8).
- OpenTelemetry tracing.
- Optional live backend (Neon or a small VM), never load-bearing.
- AWS reference deployment as IaC sketch (not deployed).

## 6. Success metrics

| Metric | Target at MVP | Target at v1.0.0 | Source |
|---|---|---|---|
| Citation precision (smoke set) | >= 0.90 | >= 0.95 | `08-eval-spec.md` |
| Citation recall (smoke set) | >= 0.80 | >= 0.90 | same |
| Numeric exactness to the cent | >= 0.95 | >= 0.98 | same |
| Refusal correctness (F1) | >= 0.85 | >= 0.90 | same |
| Anomaly recall (reconciliation, deterministic) | 1.00 on catalog types in scope | 1.00 | same |
| Tamper detection rate across tamper ladder levels 1 to 3 (ADR-0015 numbering) | 100% | 100% | property tests plus demo |
| Core module coverage | >= 85% | >= 90% | REQ-QA-08 |
| Ingest throughput (laptop, measured) | report only | report with p50/p95/p99 | `docs/reports/load-test.md` |
| Public demo first meaningful paint | n/a | < 2.5 s on 4G profile | Lighthouse |

Thresholds are starting points. The eval spec defines a ratchet: thresholds only move up.

## 7. Key user stories

- US-1. As a reviewer, I open the public link and within 10 seconds understand that answers are cryptographically traceable.
- US-2. As Maya, I ask a numeric question and get an answer where every number is clickable, shows the query that produced it, and lists the events behind it.
- US-3. As Maya, I expand a citation and click Verify; my browser recomputes the leaf hash, walks the proof path, and checks the checkpoint signature.
- US-4. As a skeptic, I edit the cited record in the tamper demo, click Verify, and watch it fail at the exact level that catches the edit.
- US-5. As a skeptic, I ask something the ledger cannot support and the analyst refuses, explaining why.
- US-6. As a data engineer, I run `make up && make seed && make demo` and watch events flow, lag stay bounded, and control totals match across Kafka, Postgres, and the lake.
- US-7. As an AI engineer, I open the eval dashboard and compare runs, including the naive baseline.

## 8. Constraints

- Solo developer, about one month, rolling-wave planning (later phases re-planned at checkpoints RP-1 and RP-2).
- No AWS account usage. Local open-source equivalents with an explicit AWS mapping (`15-aws-reference-architecture.md`).
- Public demo must not depend on any always-on free-tier service.
- LLM spend bounded by token budgets and response caching.

## 9. Open questions

Tracked in `12-risks-and-decisions-log.md` section "Open questions".
