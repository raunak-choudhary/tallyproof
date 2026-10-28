# reconciliation

Stores and serves the breaks found by the rules in `tallyproof_core/reconciliation.py`. The rules are plain Python with no Django, so they can be tested on their own; this app runs them as a projection of the log and keeps their output.

| Module | What it does |
|---|---|
| `models.py` | `recon_break` (one row per break, unique by type and triggering event) and `break_event` (which events a break involves, and in what role) |
| `projection.py` | Replays the log up to its cursor to warm the rules, then applies each new event and writes breaks plus an outbox row per break |
| `api.py` | `GET /api/v1/reconciliation/breaks` (filter by `break_type`, `award_key`) and `/breaks/{break_id}` |

Break types: `possible_duplicate_award`, `deobligation_exceeds_award`, `orphan_outlay`, `outlay_exceeds_obligation`, `late_after_close`. Settings: `RECON_AMOUNT_TOLERANCE`, `RECON_LATE_ARRIVAL_WATERMARK_HOURS`.

**Produces** `recon.breaks.v1`, through the outbox. Runs inside `make project`; rebuild with `make rebuild-derived VIEW=reconciliation`.

Tests: `tests/unit/core/test_reconciliation.py`, `tests/integration/reconciliation/`.
