from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from tallyproof_core.events import EventEnvelope
from tallyproof_pipeline.settings import get_settings
from tallyproof_pipeline.treasury import (
    PAGE_SIZE,
    TreasuryError,
    days_between,
    fetch_day,
    latest_record_date,
    outgoing,
    to_events,
)

DAY = date(2026, 10, 26)


def line(
    number: int,
    kind: str,
    category: str,
    amount: str,
    account: str = "Treasury General Account (TGA)",
) -> dict[str, str]:
    return {
        "record_date": DAY.isoformat(),
        "account_type": account,
        "transaction_type": kind,
        "transaction_catg": category,
        "transaction_today_amt": amount,
        "src_line_nbr": str(number),
    }


ROWS = [
    line(1, "Deposits", "Taxes - Withheld Individual/FICA", "9"),
    line(2, "Deposits", "Customs and Certain Excise Taxes", "17"),
    line(3, "Withdrawals", "Social Security Benefits (EFT)", "40"),
    line(4, "Withdrawals", "Unclassified", "null"),
    line(90, "Deposits", "Total", "26", account="Treasury General Account Total Deposits"),
    line(91, "Withdrawals", "Total", "41", account="Treasury General Account Total Withdrawals"),
]


@dataclass
class FakeResponse:
    body: object

    def raise_for_status(self) -> None: ...

    def json(self) -> object:
        return self.body


@dataclass
class FakeSession:
    pages: list[list[dict[str, str]]]
    calls: list[dict[str, str]] = field(default_factory=list)

    def get(self, url, params, timeout):
        self.calls.append(params)
        return FakeResponse({"data": self.pages[len(self.calls) - 1]})


def test_detail_lines_become_cash_movements_and_totals_are_checked():
    now = datetime(2026, 10, 27, 21, 0, tzinfo=UTC)
    result = to_events(ROWS, DAY, now=now)
    assert [e.payload.model_dump()["category"] for e in result.events] == [
        "Taxes - Withheld Individual/FICA",
        "Customs and Certain Excise Taxes",
        "Social Security Benefits (EFT)",
    ]
    first = result.events[0]
    assert first.idempotency_key == "fiscaldata:dts:2026-10-26:deposit:line-1"
    assert first.payload.model_dump(mode="json")["amount"] == "9.00"
    assert first.payload.model_dump()["unit"] == "millions"
    assert first.occurred_at == datetime(2026, 10, 26, tzinfo=UTC)
    assert first.emitted_at == now
    assert result.skipped == 1  # the null amount
    # One withdrawal line can be off by half a million from rounding; 40 vs 41 is more.
    assert result.total_mismatches == {"withdrawal": (Decimal(40), Decimal(41))}


def test_differences_within_rounding_are_not_reported():
    rows = [
        *ROWS[:2],
        line(90, "Deposits", "Total", "27", account="Treasury General Account Total Deposits"),
    ]
    assert to_events(rows, DAY).total_mismatches == {}  # 26 vs 27 across two rounded lines


def test_rerunning_a_day_gives_the_same_idempotency_keys():
    keys = [e.idempotency_key for e in to_events(ROWS, DAY).events]
    assert keys == [e.idempotency_key for e in to_events(ROWS, DAY).events]
    assert len(set(keys)) == len(keys)


def test_messages_are_keyed_by_the_treasury_account_and_round_trip():
    messages = list(outgoing(to_events(ROWS, DAY)))
    assert {m.key for m in messages} == {b"treasury-operating-cash"}
    assert all(EventEnvelope.model_validate_json(m.value) for m in messages)


def test_fetch_day_follows_pages_until_a_short_one():
    full = [line(i, "Deposits", f"c{i}", "1") for i in range(PAGE_SIZE)]
    session = FakeSession([full, ROWS[:2]])
    rows = fetch_day(session, get_settings(), DAY)  # type: ignore[arg-type]
    assert len(rows) == PAGE_SIZE + 2
    assert [c["page[number]"] for c in session.calls] == ["1", "2"]
    assert session.calls[0]["filter"] == "record_date:eq:2026-10-26"


def test_latest_date_and_bad_responses():
    session = FakeSession([[{"record_date": "2026-10-26"}], []])
    assert latest_record_date(session, get_settings()) == DAY  # type: ignore[arg-type]
    with pytest.raises(TreasuryError, match="no statements"):
        latest_record_date(session, get_settings())  # type: ignore[arg-type]
    broken = FakeSession([])
    broken.get = lambda url, params, timeout: FakeResponse({"error": "x"})  # type: ignore[method-assign]
    with pytest.raises(TreasuryError, match="no data"):
        fetch_day(broken, get_settings(), DAY)  # type: ignore[arg-type]


def test_days_between_is_inclusive():
    assert list(days_between(date(2026, 1, 30), date(2026, 2, 1))) == [
        date(2026, 1, 30),
        date(2026, 1, 31),
        date(2026, 2, 1),
    ]
