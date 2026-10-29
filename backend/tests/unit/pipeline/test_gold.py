from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from tallyproof_core.events import EventType, ObligationAdjusted, ObligationRecorded
from tallyproof_pipeline.gold import conform, read_events, write_events


def silver_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "contract_transaction_unique_key": "9700_-NONE-_FA860121C0001_0_-NONE-_0",
        "contract_award_unique_key": "CONT_AWD_FA860121C0001_9700_-NONE-_-NONE-",
        "award_id_piid": "FA860121C0001",
        "modification_number": "0",
        "federal_action_obligation": Decimal("1250000.00"),
        "action_date": date(2025, 3, 14),
        "last_modified_date": datetime(2025, 3, 20, 4, 28, 7),
        "initial_report_date": datetime(2025, 3, 15, 13, 7, 48),
        "awarding_agency_name": "Department of Defense",
        "funding_agency_name": "Department of the Air Force",
        "recipient_uei": "ZQGGHJH74DW7",
        "transaction_description": "ENGINEERING SERVICES",
        "action_type": None,
        "naics_code": "541330",
        "product_or_service_code": "R425",
    }
    row.update(overrides)
    return row


def test_base_award_becomes_obligation_recorded():
    event = conform(silver_row(), seed=1)
    assert event.event_type is EventType.OBLIGATION_RECORDED
    assert isinstance(event.payload, ObligationRecorded)
    assert event.payload.amount == "1250000.00"
    assert event.payload.naics_code == "541330"
    assert event.account_id == "ZQGGHJH74DW7"


def test_modification_becomes_obligation_adjusted_and_keeps_negative_amounts():
    event = conform(
        silver_row(modification_number="P00004", federal_action_obligation=Decimal("-5000.00")),
        seed=1,
    )
    assert event.event_type is EventType.OBLIGATION_ADJUSTED
    assert isinstance(event.payload, ObligationAdjusted)
    assert event.payload.amount == "-5000.00"
    assert event.payload.modification_number == "P00004"


def test_timing_reflects_when_the_government_first_reported_it():
    event = conform(silver_row(), seed=1)
    document = event.leaf_document()
    assert document["occurred_at"] == "2025-03-14T00:00:00Z"
    assert document["emitted_at"] == "2025-03-15T13:07:48Z"


def test_a_later_edit_does_not_make_a_transaction_look_late():
    # Real FY2024 rows downloaded in 2026 carry 2025 and 2026 edit times. Using them
    # made three in four transactions look reported a year after they happened.
    edited = silver_row(last_modified_date=datetime(2026, 9, 1))
    assert conform(edited, seed=1).emitted_at == datetime(2025, 3, 15, 13, 7, 48, tzinfo=UTC)


def test_the_last_edit_is_used_only_when_the_first_report_time_is_missing():
    event = conform(silver_row(initial_report_date=None), seed=1)
    assert event.emitted_at == datetime(2025, 3, 20, 4, 28, 7, tzinfo=UTC)


def test_plain_report_dates_and_aware_timestamps_are_both_accepted():
    plain = silver_row(initial_report_date=date(2025, 3, 21))
    assert conform(plain, seed=1).emitted_at == datetime(2025, 3, 21, tzinfo=UTC)
    aware = datetime(2025, 3, 22, 8, 0, tzinfo=UTC)
    assert conform(silver_row(initial_report_date=aware), seed=1).emitted_at == aware


def test_report_date_before_action_date_is_clamped_to_the_action_date():
    event = conform(silver_row(initial_report_date=date(2025, 1, 1)), seed=1)
    assert event.emitted_at == event.occurred_at


def test_same_row_and_seed_give_identical_events_and_hashes():
    first, second = conform(silver_row(), seed=7), conform(silver_row(), seed=7)
    assert first.event_id == second.event_id
    assert first.leaf_hash() == second.leaf_hash()


def test_different_seed_gives_a_different_event_id():
    assert conform(silver_row(), seed=1).event_id != conform(silver_row(), seed=2).event_id


def test_idempotency_key_comes_from_the_transaction_key():
    event = conform(silver_row(), seed=1)
    assert event.idempotency_key == "usaspending:9700_-NONE-_FA860121C0001_0_-NONE-_0"


def test_missing_amount_becomes_zero_and_empty_optionals_are_omitted():
    event = conform(
        silver_row(federal_action_obligation=None, naics_code="  ", funding_agency_name=None),
        seed=1,
    )
    payload = event.leaf_document()["payload"]
    assert isinstance(payload, dict)
    assert payload["amount"] == "0.00"
    assert "naics_code" not in payload
    assert "funding_agency" not in payload


def test_rows_that_cannot_form_events_are_rejected():
    with pytest.raises(TypeError, match="action_date"):
        conform(silver_row(action_date="2025-03-14"), seed=1)
    with pytest.raises(TypeError, match="dates or timestamps"):
        conform(silver_row(initial_report_date="soon"), seed=1)
    with pytest.raises(ValidationError):
        conform(silver_row(recipient_uei=""), seed=1)


def test_events_round_trip_through_gzip_json_lines(tmp_path):
    events = [
        conform(silver_row(contract_transaction_unique_key=f"T{i}"), seed=1) for i in range(3)
    ]
    path = tmp_path / "gold" / "events.jsonl.gz"
    assert write_events(events, path) == 3
    restored = list(read_events(path))
    assert [e.leaf_hash() for e in restored] == [e.leaf_hash() for e in events]


def test_contact_details_are_removed_from_descriptions():
    row = silver_row(
        transaction_description="FILING CABINET. POC JANE.DOE@EXAMPLE.MIL (O) 301-555-0112"
    )
    event = conform(row, seed=1)
    assert isinstance(event.payload, ObligationRecorded)
    assert event.payload.description == (
        "FILING CABINET. POC [contact removed] (O) [contact removed]"
    )
    plain = conform(silver_row(transaction_description=None), seed=1)
    assert isinstance(plain.payload, ObligationRecorded)
    assert plain.payload.description is None
