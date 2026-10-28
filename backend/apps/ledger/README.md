# ledger

The append-only event store, the Merkle log built over it, signed checkpoints, and everything derived from the log.

| Module | What it does |
|---|---|
| `models.py` | Tables: `ledger_event`, `ledger_batch`, `merkle_log_head`, `outbox`, `journal_line`, `projection_cursor` |
| `append.py` | Appends a batch with gap-free leaf indexes from a locked counter row |
| `checkpointer.py` | Closes batches by size or age, signs C2SP checkpoints, exports witness copies, and requests OpenTimestamps proofs (`timestamps.py`) |
| `witness.py` | Checks exported checkpoints against the pinned key and the current log |
| `projections.py` | Runs derived views in leaf order with a cursor per view: `appended`, `journal`, `reconciliation` ([ADR-0019](../../../docs/adr/0019-projections-read-the-ledger.md)) |
| `outbox.py` | Relays outbox rows to Kafka, at least once, and measures how far behind it is |
| `derived.py` | Compares the journal with a fresh rebuild, and clears a view so it's rebuilt |
| `tamper.py` | The local tamper demo, levels 1 to 3, with restore |
| `api/` | Events, proofs, checkpoints, and consistency proofs. Proofs, never verdicts |

Append-only tables are protected three ways: the app role has no update or delete grants, triggers reject changes, and `TRUNCATE` is revoked.

**Produces** `ledger.appended.v1` and `ledger.checkpoints.v1`, through the outbox. Sends `ledger_appended` and `outbox_ready` Postgres notifications that wake the workers.

| Command | Make target |
|---|---|
| `checkpointer` | `make checkpointer` |
| `project` | `make project` |
| `relay_outbox` | `make relay` |
| `check_derived`, `rebuild_derived` | `make check-derived`, `make rebuild-derived VIEW=` |
| `verify_event`, `verify_witness` | `make verify-event`, `make verify-witness` |
| `tamper` | `make tamper LEVEL= EVENT=` or `RESTORE=1` |

Tests: `tests/integration/ledger/`, `tests/integration/api/`.
