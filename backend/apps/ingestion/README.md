# ingestion

Reads raw events from Kafka and appends them to the ledger exactly once ([ADR-0008](../../../docs/adr/0008-effectively-once-ingestion.md)).

| Module | What it does |
|---|---|
| `consumer.py` | The poll loop: validate, deduplicate, append, and store offsets in one transaction |
| `dedupe.py` | Per-partition Bloom filters in front of the database's unique idempotency key, rebuilt from the ledger on partition assignment |
| `offsets.py` | Consumer offsets in Postgres, fenced by a generation number so a stale consumer can't move them back |
| `dead_letter.py` | Wraps a record that failed validation with the reason and its source coordinates |
| `control_totals.py` | Reads a topic range back and compares counts, amounts, and leaf hashes with the ledger |
| `schemas.py` | Exports the event JSON Schema and registers it with backward compatibility |

**Consumes** `fin.events.raw.v1`. **Produces** `fin.events.dlq.v1` (invalid records) and ledger rows through `apps.ledger.append`.

| Command | Make target |
|---|---|
| `ingest` | `make ingest` |
| `dead_letters` | `make dead-letters` (`EXPORT=` or `REPLAY=` a file) |
| `check_totals` | `make check-totals` |
| `register_schemas` | `make register-schemas` |

Tests: `tests/unit/ingestion/`, `tests/integration/ingestion/`.
