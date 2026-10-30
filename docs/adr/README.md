# Architecture decision records

Each record explains the context, the decision, the reasons, the alternatives considered, and the consequences. A record's status is Proposed, Accepted, or Superseded. Significant decisions get a record when they're made, and a decision is changed by writing a new record, not by editing the old one.

| ADR | Title | Status |
|---|---|---|
| 0001 | PostgreSQL over NoSQL for the ledger | Accepted |
| 0002 | Redpanda as the local Kafka-compatible broker | Accepted |
| 0003 | Merkle log structure and batching policy | Accepted |
| 0004 | Django 5.2 LTS | Accepted; its WebSocket server was changed by 0018 |
| 0005 | Replay mode for the public demo | Accepted |
| 0006 | Project name | Accepted |
| 0007 | Signed checkpoints and external witnessing | Accepted |
| 0008 | Effectively-once ingestion with Bloom fast path | Accepted |
| 0009 | Bound-claim answer format | Accepted |
| 0010 | RFC 8785 canonical JSON for leaf bytes | Accepted |
| 0011 | release-please on a minimal GitHub Action | Accepted |
| 0012 | Parquet lake on SeaweedFS | Accepted, amended: Iceberg on local disk |
| 0013 | Derive a double-entry journal from events | Accepted |
| 0014 | Constrained query IR compiled to SQL | Accepted |
| 0015 | Verification trust model | Accepted |
| 0016 | Real public spending data with a labeled synthetic overlay | Accepted |
| 0017 | PySpark 4.1 batch processing with Deequ data quality | Accepted |
| 0018 | Uvicorn instead of Daphne for the WebSocket server | Accepted |
| 0019 | Derived state is projected from the ledger, not consumed from Kafka | Accepted |
| 0020 | GitHub Pages for the public demo, deployed by GitHub Actions | Accepted |
| 0021 | One OpenAI-compatible model client, running on Groq's free tier | Accepted |
| 0022 | fastembed and an in-memory index for policy retrieval | Accepted |
| 0023 | Evaluation runs are recorded as reports, in a throwaway ledger | Accepted |
| 0024 | A Merkle-sum tree for provable totals | Accepted |
| 0025 | Recipient bursts with Count-Min Sketches | Accepted |
