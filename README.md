# Ledgerline

A streaming financial ledger with an AI analyst whose every claim is cited to an exact source event, along with a cryptographic proof that the record hasn't been changed since ingestion. Answer quality is measured against exact ground truth.

> **Status: planning (Phase 0).** Nothing runs yet. The design, the decisions, and the day-by-day plan are in [`docs/`](docs/). This banner will always say exactly what works.

<!-- Hero diagram and tamper-demo GIF land in Phase 5 (E-510). -->

## The idea in one paragraph

Events (invoices, payments, refunds) stream through Kafka into an append-only Postgres ledger. Each accepted event becomes a leaf in an [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162.html) Merkle log. Checkpoints of that log are signed with Ed25519 and copied somewhere outside the database. When the analyst answers a question, it never types a number itself. Values are bound from executed SQL, and every claim cites the events behind it. Your browser fetches the proofs and checks them itself, so you don't have to trust the server. Change one cent in a cited record and verification fails, and the demo shows you which mechanism caught it.

## Why this exists

- **LLM citations are often unfaithful.** Wallat et al. (ICTIR 2025) found that up to 57% of citations in attributed RAG answers were not faithful: the model had not actually relied on the cited source. Gao et al. (ALCE, EMNLP 2023) report that even the best models lacked complete citation support 50% of the time on ELI5.
- **Finance QA is hard, numbers especially.** On a 150-question sample of FinanceBench (Islam et al., 2023), GPT-4-Turbo with retrieval answered incorrectly or refused 81% of questions.
- **Regulators are paying attention.** FINRA's 2026 Annual Regulatory Oversight Report added a generative AI section. It names accuracy (including hallucinations) and bias as risks, and lists storing prompt and output logs as an effective practice. The EU AI Act's Articles 12 and 14 describe automatic event logging and human oversight for high-risk AI systems. After the 2026 Digital Omnibus amendments, those obligations apply from December 2027 or August 2028 depending on the category. This project is motivated by those expectations. It does not claim compliance with any of them.
- **The AWS gap.** Amazon QLDB reached end of support on July 31, 2025, and AWS recommends Aurora PostgreSQL instead. AWS's migration guidance notes that Aurora PostgreSQL does not keep a permanent, immutable record of changes, so that history has to be generated separately. This project is a working example of that pattern on Postgres.

Every source, with exact quotes and links, is in [`docs/research/verified-sources.md`](docs/research/verified-sources.md).

## What is different from existing work

[answerproof](https://github.com/AgentPostmortem/Answerproof) issues signed receipts with a Merkle root over a RAG retrieval set. It's a good idea, and it shows that "Merkle-verified citations" alone isn't new. Ledgerline differs in three ways:

1. **Provenance from ingestion.** Proofs are anchored to streamed events as they arrive, in an append-only log with consistency proofs, so they show that the source record itself is unchanged, not just that it was retrieved.
2. **Exact ground-truth evals.** Our generator injects labeled anomalies, so expected answers and expected citations are exact. They don't come from an LLM judge.
3. **Numeric claims are bound, not checked after the fact.** The model writes slots, the ledger fills them, and a verifier rejects any number the model typed itself.

## Quickstart

Coming in Phase 1. The target is three commands:

```bash
cp .env.example .env && make keygen   # fill secrets
make up
make seed SCENARIO=demo
```

## Architecture

See [`docs/07-architecture.md`](docs/07-architecture.md). In short: generator, then Redpanda, then ingestion (schema validation, Bloom-filter fast path, and a UNIQUE constraint, with consumer offsets stored in the same transaction), then the append-only ledger and Merkle log, then signed checkpoints, then an outbox feeding reconciliation, the journal, the lake sink, and the UI. The analyst sits on top and uses a read-only database role.

## Eval results

None yet. Results will be published here by CI, along with model IDs, date, set size, and the git SHA.

## Design decisions

Architecture Decision Records are in [`docs/adr/`](docs/adr/).

## Related work

- RFC 9162, Certificate Transparency 2.0 (Merkle log hashing, inclusion and consistency proofs)
- RFC 8785, JSON Canonicalization Scheme
- Crosby and Wallach, *Efficient Data Structures for Tamper-Evident Logging*, USENIX Security 2009
- C2SP `tlog-checkpoint` and transparency.dev
- answerproof (see above)
- VeriRAG (IACR ePrint 2026/637), zero-knowledge proofs for verifiable RAG, a direction for future work

## License

MIT
