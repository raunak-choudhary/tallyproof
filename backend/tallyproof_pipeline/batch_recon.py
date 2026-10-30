"""Reconciliation as SQL in DuckDB, compared with the streaming rules.

The streaming engine (:mod:`tallyproof_core.reconciliation`) reads one event at a
time and keeps running state. The same rules can be written as set-based SQL over
the whole history at once. Running both over the same gold events shows where they
agree and where their notion of a window differs; running the SQL over the 13
million cleaned transactions in silver shows what the batch path costs at scale.

Rules in SQL, each mirroring its streaming counterpart in log order:

- ``possible_duplicate_award``: a new award whose recipient, amount, and action
  date match the first award with that signature, under a different award key.
- ``deobligation_exceeds_award``: a de-obligation that takes an award's running
  obligations below zero.
- ``orphan_outlay``: an outlay that is the first event the log has for its award.
- ``outlay_exceeds_obligation``: an outlay after which the award's latest
  cumulative outlays, per Treasury account and fiscal year, exceed its obligations.
- ``late_after_close``: an event that arrived more than 72 hours after it happened.
- ``recipient_burst``: eight or more new awards to one recipient within any 60
  minutes, after 30 days with none. The SQL counts over a sliding hour exactly;
  the stream counts in fixed windows with sketches (ADR-0025).

Usage::

    python -m tallyproof_pipeline.batch_recon         # make batch-recon
"""

import json
import time
from pathlib import Path
from typing import Any

import duckdb

from tallyproof_core.reconciliation import Reconciler
from tallyproof_pipeline.gold import read_events
from tallyproof_pipeline.settings import get_settings

LOAD_GOLD = """
CREATE OR REPLACE TABLE raw AS
SELECT * FROM read_json(?, format = 'newline_delimited', columns = {
  event_id: 'VARCHAR', idempotency_key: 'VARCHAR', event_type: 'VARCHAR',
  occurred_at: 'TIMESTAMPTZ', emitted_at: 'TIMESTAMPTZ', account_id: 'VARCHAR', payload: 'VARCHAR'
})
"""

LOAD_EVENTS = (
    # rowid is insertion order, which is the file's order: the log order.
    """
CREATE OR REPLACE TABLE numbered AS
SELECT rowid AS pos, idempotency_key, event_id, event_type, occurred_at, emitted_at, account_id,
       json_extract_string(payload, '$.award_key') AS award_key,
       CAST(json_extract_string(payload, '$.amount') AS DECIMAL(19, 2)) AS amount,
       json_extract_string(payload, '$.amount') AS amount_text,
       json_extract_string(payload, '$.action_date') AS action_date,
       json_extract_string(payload, '$.treasury_account') AS treasury_account,
       CAST(json_extract_string(payload, '$.fiscal_year') AS INTEGER) AS fiscal_year,
       CAST(json_extract_string(payload, '$.cumulative_outlay') AS DECIMAL(19, 2))
         AS cumulative_outlay
FROM raw
""",
    # The ledger refuses a repeated idempotency key; keep each key's first delivery.
    """
CREATE OR REPLACE TABLE ev AS
SELECT * EXCLUDE (idempotency_key) FROM numbered
QUALIFY row_number() OVER (PARTITION BY idempotency_key ORDER BY pos) = 1
""",
)

GOLD_RULES: dict[str, str] = {
    "possible_duplicate_award": """
        WITH signed AS (
          SELECT pos, event_id, award_key,
                 first_value(award_key) OVER w AS first_award,
                 first_value(pos) OVER w AS first_pos
          FROM ev
          WHERE event_type = 'obligation.recorded' AND amount <> 0
          WINDOW w AS (PARTITION BY account_id, amount_text, action_date ORDER BY pos)
        )
        SELECT event_id FROM signed WHERE pos > first_pos AND award_key <> first_award""",
    "deobligation_exceeds_award": """
        WITH running AS (
          SELECT event_id, event_type, amount,
                 sum(amount) OVER (PARTITION BY award_key ORDER BY pos) AS obligated
          FROM ev WHERE event_type IN ('obligation.recorded', 'obligation.adjusted')
        )
        SELECT event_id FROM running
        WHERE event_type = 'obligation.adjusted' AND amount < 0 AND obligated < 0""",
    "orphan_outlay": """
        SELECT event_id FROM (
          SELECT event_id, event_type, pos, min(pos) OVER (PARTITION BY award_key) AS first_pos
          FROM ev
        ) WHERE event_type = 'outlay.reported' AND pos = first_pos""",
    "outlay_exceeds_obligation": """
        WITH award_events AS (
          SELECT pos, event_id, event_type, award_key,
                 CASE WHEN event_type LIKE 'obligation.%' THEN amount ELSE 0 END AS obligation,
                 CASE WHEN event_type = 'outlay.reported'
                      THEN cumulative_outlay - coalesce(lag(cumulative_outlay) OVER (
                        PARTITION BY award_key, treasury_account, fiscal_year ORDER BY pos), 0)
                      ELSE 0 END AS outlay_change
          FROM ev
        ), running AS (
          SELECT *, min(pos) OVER (PARTITION BY award_key) AS first_pos,
                 sum(obligation) OVER (PARTITION BY award_key ORDER BY pos) AS obligated,
                 sum(outlay_change) OVER (PARTITION BY award_key ORDER BY pos) AS outlaid
          FROM award_events
        )
        SELECT event_id FROM running
        WHERE event_type = 'outlay.reported' AND pos > first_pos AND outlaid - obligated > 0""",
    "late_after_close": """
        SELECT event_id FROM ev WHERE emitted_at - occurred_at > INTERVAL 72 HOUR""",
    "recipient_burst": """
        WITH awards AS (
          SELECT event_id, account_id, emitted_at,
                 count(*) OVER w AS in_hour, min(emitted_at) OVER w AS hour_start
          FROM ev WHERE event_type = 'obligation.recorded'
          WINDOW w AS (PARTITION BY account_id ORDER BY emitted_at
                       RANGE BETWEEN INTERVAL 3599 SECOND PRECEDING AND CURRENT ROW)
        ), crossings AS (
          SELECT * FROM awards WHERE in_hour = 8
        )
        SELECT c.event_id FROM crossings c
        WHERE NOT EXISTS (
          SELECT 1 FROM ev p
          WHERE p.event_type = 'obligation.recorded' AND p.account_id = c.account_id
            AND p.emitted_at >= date_trunc('day', c.hour_start) - INTERVAL 30 DAY
            AND p.emitted_at < date_trunc('day', c.hour_start)
        )""",
}

SILVER_RULES: dict[str, str] = {
    "possible_duplicate_award": """
        WITH new_awards AS (
          SELECT contract_award_unique_key AS award, recipient_uei, federal_action_obligation,
                 action_date, initial_report_date, contract_transaction_unique_key AS tx
          FROM silver WHERE modification_number = '0' AND federal_action_obligation <> 0
        )
        SELECT count(*) FROM (
          SELECT award, tx,
                 first_value(award) OVER w AS first_award, first_value(tx) OVER w AS first_tx
          FROM new_awards
          WINDOW w AS (PARTITION BY recipient_uei, federal_action_obligation, action_date
                       ORDER BY initial_report_date, tx)
        ) WHERE tx <> first_tx AND award <> first_award""",
    "deobligation_exceeds_award": """
        SELECT count(*) FROM (
          SELECT federal_action_obligation AS amount,
                 sum(federal_action_obligation) OVER (
                   PARTITION BY contract_award_unique_key
                   ORDER BY action_date, modification_number, contract_transaction_unique_key
                 ) AS obligated
          FROM silver
        ) WHERE amount < 0 AND obligated < 0""",
    "recipient_burst": """
        WITH awards AS (
          SELECT recipient_uei, initial_report_date AS reported,
                 count(*) OVER w AS in_hour, min(initial_report_date) OVER w AS hour_start
          FROM silver WHERE modification_number = '0' AND recipient_uei IS NOT NULL
          WINDOW w AS (PARTITION BY recipient_uei ORDER BY initial_report_date
                       RANGE BETWEEN INTERVAL 3599 SECOND PRECEDING AND CURRENT ROW)
        )
        SELECT count(*) FROM awards a
        WHERE a.in_hour = 8 AND NOT EXISTS (
          SELECT 1 FROM silver p
          WHERE p.modification_number = '0' AND p.recipient_uei = a.recipient_uei
            AND p.initial_report_date >= date_trunc('day', a.hour_start) - INTERVAL 30 DAY
            AND p.initial_report_date < date_trunc('day', a.hour_start)
        )""",
}


def batch_gold(con: duckdb.DuckDBPyConnection, events: Path) -> dict[str, set[str]]:
    """Trigger event IDs per rule, computed in SQL over the gold events."""
    con.execute(LOAD_GOLD, [str(events)])
    for statement in LOAD_EVENTS:
        con.execute(statement)
    return {
        rule: {str(row[0]) for row in con.execute(sql).fetchall()}
        for rule, sql in GOLD_RULES.items()
    }


def streaming_gold(events: Path) -> dict[str, set[str]]:
    """Trigger event IDs per rule from the streaming engine, over the same events."""
    engine = Reconciler()
    seen: set[str] = set()
    out: dict[str, set[str]] = {rule: set() for rule in GOLD_RULES}
    for event in read_events(events):
        if event.idempotency_key in seen:
            continue
        seen.add(event.idempotency_key)
        for b in engine.apply(event):
            out.setdefault(b.break_type.value, set()).add(b.trigger_event_id)
    return out


def compare(batch: dict[str, set[str]], stream: dict[str, set[str]]) -> dict[str, dict[str, int]]:
    """Per rule: breaks both found, and those only one of them found."""
    return {
        rule: {
            "batch": len(batch.get(rule, set())),
            "streaming": len(stream.get(rule, set())),
            "both": len(batch.get(rule, set()) & stream.get(rule, set())),
            "only_batch": len(batch.get(rule, set()) - stream.get(rule, set())),
            "only_streaming": len(stream.get(rule, set()) - batch.get(rule, set())),
        }
        for rule in GOLD_RULES
    }


def silver_counts(con: duckdb.DuckDBPyConnection, silver_glob: str) -> dict[str, Any]:
    """Each silver rule's break count and how long it took."""
    con.execute(f"CREATE OR REPLACE VIEW silver AS SELECT * FROM read_parquet('{silver_glob}')")  # noqa: S608 - a configured path
    rows = int(con.execute("SELECT count(*) FROM silver").fetchone()[0])  # type: ignore[index]
    out: dict[str, Any] = {"rows": rows, "rules": {}}
    for rule, sql in SILVER_RULES.items():
        started = time.monotonic()
        count = int(con.execute(sql).fetchone()[0])  # type: ignore[index]
        out["rules"][rule] = {"breaks": count, "seconds": round(time.monotonic() - started, 1)}
    return out


def main() -> None:  # pragma: no cover - exercised by make batch-recon
    """Compare batch and streaming on gold, run the batch rules on silver, write a report."""
    settings = get_settings()
    events = settings.gold_dir / "events.jsonl.gz"
    # Kept small so a laptop stays cool: two threads and 2 GB, spilling to disk past that.
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    started = time.monotonic()
    batch = batch_gold(con, events)
    batch_seconds = time.monotonic() - started
    started = time.monotonic()
    stream = streaming_gold(events)
    stream_seconds = time.monotonic() - started
    report = {
        "gold": {
            "batch_seconds": round(batch_seconds, 1),
            "streaming_seconds": round(stream_seconds, 1),
            "rules": compare(batch, stream),
        },
        "silver": silver_counts(con, str(settings.silver_dir / "contracts" / "**" / "*.parquet")),
    }
    out = settings.data_dir / "batch_recon.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
