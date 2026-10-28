"""Live connector for the Daily Treasury Statement (deposits and withdrawals of cash).

Each business day the Treasury publishes every deposit to and withdrawal from
its operating cash account, by category, through the keyless Fiscal Data API.
This connector turns each detail line into a ``cash.movement`` event and
publishes it to the raw topic, the same way the replay producer publishes
contract events.

Reruns are safe: each line's idempotency key is built from the record date,
direction, and the statement's own line number, so the ledger refuses a line it
already has. The statement's total lines are not published; they are used to
check that the detail lines add up.

Usage::

    python -m tallyproof_pipeline.treasury --since 2026-10-01
    python -m tallyproof_pipeline.treasury --follow
"""

import argparse
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urljoin

import requests

from tallyproof_core.events import EventEnvelope
from tallyproof_core.ids import new_id
from tallyproof_pipeline.settings import PipelineSettings, get_settings
from tallyproof_pipeline.stream import Outgoing, partition_key

log = logging.getLogger(__name__)

ENDPOINT = "v1/accounting/dts/deposits_withdrawals_operating_cash"
ACCOUNT_ID = "treasury-operating-cash"
PAGE_SIZE = 1000
DIRECTIONS = {"Deposits": "deposit", "Withdrawals": "withdrawal"}
PUBLISHED_AFTER = timedelta(days=1, hours=21)
"""Statements appear around 4 pm Eastern (21:00 UTC) on the next business day."""


class TreasuryError(RuntimeError):
    """The API answered with something this connector can't use."""


@dataclass(frozen=True)
class DayResult:
    """One statement day turned into events."""

    record_date: date
    events: list[EventEnvelope]
    skipped: int
    total_mismatches: dict[str, tuple[Decimal, Decimal]]
    """direction -> (sum of detail lines, reported total), where they differ by more
    than rounding allows. Each line is rounded to the nearest million on its own,
    so n lines may drift from the total by up to n/2 million."""


def _get(
    session: requests.Session, settings: PipelineSettings, params: dict[str, str]
) -> list[dict[str, str]]:
    url = urljoin(str(settings.fiscaldata_api_url), ENDPOINT)
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise TreasuryError("the API response has no data list")
    rows: list[dict[str, str]] = body["data"]
    return rows


def latest_record_date(session: requests.Session, settings: PipelineSettings) -> date:
    """The newest statement date the API has."""
    rows = _get(
        session, settings, {"sort": "-record_date", "page[size]": "1", "fields": "record_date"}
    )
    if not rows:
        raise TreasuryError("the API returned no statements")
    return date.fromisoformat(rows[0]["record_date"])


def fetch_day(
    session: requests.Session, settings: PipelineSettings, record_date: date
) -> list[dict[str, str]]:
    """Every row of one day's statement, across pages."""
    rows: list[dict[str, str]] = []
    page = 1
    while True:
        page_rows = _get(
            session,
            settings,
            {
                "filter": f"record_date:eq:{record_date.isoformat()}",
                "page[size]": str(PAGE_SIZE),
                "page[number]": str(page),
            },
        )
        rows.extend(page_rows)
        if len(page_rows) < PAGE_SIZE:
            return rows
        page += 1


def _is_total(row: dict[str, str]) -> bool:
    return "total" in row.get("account_type", "").lower()


def _amount(row: dict[str, str]) -> Decimal | None:
    raw = row.get("transaction_today_amt", "")
    if raw in ("", "null"):
        return None
    return Decimal(raw)


def to_events(
    rows: list[dict[str, str]], record_date: date, now: datetime | None = None
) -> DayResult:
    """Turn one day's rows into events, and check the detail lines against the totals."""
    occurred = datetime.combine(record_date, datetime.min.time(), tzinfo=UTC)
    # When Treasury published the statement (about 4 pm Eastern the next day), not
    # when we fetched it: otherwise a backfilled week would look like late reports.
    published = occurred + PUBLISHED_AFTER
    emitted = min(published, (now or datetime.now(UTC)).replace(microsecond=0))
    events: list[EventEnvelope] = []
    sums = {"deposit": Decimal(0), "withdrawal": Decimal(0)}
    lines = {"deposit": 0, "withdrawal": 0}
    totals: dict[str, Decimal] = {}
    skipped = 0
    for row in rows:
        direction = DIRECTIONS.get(row.get("transaction_type", ""))
        amount = _amount(row)
        if direction is None or amount is None:
            skipped += 1
            continue
        if _is_total(row):
            totals[direction] = amount
            continue
        sums[direction] += amount
        lines[direction] += 1
        line = row.get("src_line_nbr", "")
        events.append(
            EventEnvelope.model_validate(
                {
                    "event_id": new_id("evt", now=emitted),
                    "idempotency_key": f"fiscaldata:dts:{record_date}:{direction}:line-{line}",
                    "event_type": "cash.movement",
                    "occurred_at": occurred,
                    "emitted_at": emitted,
                    "account_id": ACCOUNT_ID,
                    "correlation_id": f"dts-{record_date}",
                    "payload": {
                        "record_date": record_date,
                        "account": row["account_type"],
                        "direction": direction,
                        "category": row["transaction_catg"],
                        "amount": str(amount),
                    },
                }
            )
        )
    mismatches = {
        direction: (sums[direction], total)
        for direction, total in totals.items()
        if abs(sums[direction] - total) > Decimal(lines[direction]) / 2
    }
    return DayResult(record_date, events, skipped, mismatches)


def outgoing(result: DayResult) -> Iterator[Outgoing]:
    """Messages for the replay producer's publisher."""
    for event in result.events:
        yield Outgoing(partition_key(event), event.model_dump_json().encode(), valid=True)


def days_between(start: date, end: date) -> Iterator[date]:
    """Every calendar day from ``start`` to ``end``; days without a statement return no rows."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def main() -> None:  # pragma: no cover - thin command-line wrapper around tested functions
    """Publish statement days to the raw topic."""
    from confluent_kafka import Producer

    from tallyproof_pipeline.stream import publish

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=date.fromisoformat, help="first statement date to publish")
    parser.add_argument("--follow", action="store_true", help="keep checking for new statements")
    args = parser.parse_args()
    producer = Producer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "acks": "all",
            "enable.idempotence": True,
        }
    )
    with requests.Session() as session:
        latest = latest_record_date(session, settings)
        start = args.since or latest
        while True:
            for day in days_between(start, latest):
                rows = fetch_day(session, settings, day)
                if not rows:
                    continue
                result = to_events(rows, day)
                summary = publish(outgoing(result), producer, settings.kafka_topic_events_raw, 1000)
                log.info("%s: published %d cash movements", day, summary.events)
                for direction, (summed, total) in result.total_mismatches.items():
                    log.warning(
                        "%s %s lines sum to %s, statement total %s", day, direction, summed, total
                    )
            if not args.follow:
                return
            start = latest + timedelta(days=1)
            time.sleep(settings.treasury_poll_seconds)
            latest = latest_record_date(session, settings)


if __name__ == "__main__":  # pragma: no cover
    main()
