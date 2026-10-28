import json
import random
from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from tallyproof_core.events import LEAF_FIELDS, EventEnvelope, EventType, ObligationRecorded
from tallyproof_core.ids import new_id

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
EVENT_ID = new_id("evt", now=NOW, rng=random.Random(7))


def obligation(**overrides: Any) -> dict[str, Any]:
    payload = {
        "award_key": "CONT_AWD_75N95021C00001_7529_-NONE-_-NONE-",
        "piid": "75N95021C00001",
        "awarding_agency": "Department of Health and Human Services",
        "amount": "125000",
        "action_date": "2025-03-14",
        "description": "LABORATORY ANALYSIS SERVICES",
    }
    envelope = {
        "event_id": EVENT_ID,
        "idempotency_key": "usaspending:CONT_TX_1",
        "event_type": "obligation.recorded",
        "occurred_at": "2025-03-14T00:00:00Z",
        "emitted_at": "2025-03-15T09:30:00+00:00",
        "account_id": "ZQGGHJH74DW7",
        "correlation_id": "corr-1",
        "payload": payload,
    }
    envelope.update(overrides)
    return envelope


def test_valid_event_parses_and_normalizes_money():
    event = EventEnvelope.model_validate(obligation())
    assert isinstance(event.payload, ObligationRecorded)
    assert event.payload.amount == "125000.00"
    assert event.payload.action_date == date(2025, 3, 14)


def test_leaf_document_has_exactly_the_hashed_fields():
    document = EventEnvelope.model_validate(obligation()).leaf_document()
    assert tuple(document) == LEAF_FIELDS
    assert "correlation_id" not in document


def test_correlation_id_does_not_change_the_leaf_hash():
    first = EventEnvelope.model_validate(obligation(correlation_id="a"))
    second = EventEnvelope.model_validate(obligation(correlation_id="b"))
    assert first.leaf_hash() == second.leaf_hash()


def test_timestamps_are_written_in_one_utc_format():
    document = EventEnvelope.model_validate(
        obligation(emitted_at="2025-03-15T05:30:00-04:00")
    ).leaf_document()
    assert document["emitted_at"] == "2025-03-15T09:30:00Z"


def test_canonical_bytes_round_trip_through_json():
    event = EventEnvelope.model_validate(obligation())
    assert json.loads(event.canonical_bytes())["payload"]["amount"] == "125000.00"


def test_absent_optional_fields_are_left_out_of_the_leaf():
    payload = EventEnvelope.model_validate(obligation()).leaf_document()["payload"]
    assert isinstance(payload, dict)
    assert "funding_agency" not in payload


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"event_id": "evt_bad"}, "valid ID"),
        ({"event_id": new_id("ans", now=NOW, rng=random.Random(1))}, "expected a evt_"),
        ({"event_type": "invoice.issued"}, "event_type"),
        ({"occurred_at": "2025-03-14T00:00:00"}, "timezone aware"),
        ({"schema_version": 2}, "schema_version"),
        ({"unexpected": "field"}, "Extra inputs"),
    ],
)
def test_invalid_envelopes_are_rejected(overrides, message):
    with pytest.raises(ValidationError, match=message):
        EventEnvelope.model_validate(obligation(**overrides))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("amount", 125000.5, "string"),
        ("amount", "1.2e5", "plain decimal"),
        ("amount", "10.005", "precision"),
        ("currency", "EUR", "USD"),
        ("description", "lone \ud800 surrogate", "unicode"),
        ("award_key", "", "at least 1"),
        ("extra", "x", "Extra inputs"),
    ],
)
def test_invalid_payloads_are_rejected(field, value, message):
    event = obligation()
    event["payload"][field] = value
    with pytest.raises(ValidationError, match=message):
        EventEnvelope.model_validate(event)


def test_payload_must_match_the_declared_event_type():
    event = obligation(event_type="cash.movement")
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(event)


def test_payload_model_of_the_wrong_type_is_rejected():
    from tallyproof_core.events import CashMovement

    cash = CashMovement(
        record_date=date(2025, 1, 2),
        account="Treasury General Account",
        direction="deposit",
        category="Taxes - Individual",
        amount="1234",
    )
    with pytest.raises(ValidationError, match="not a ObligationRecorded"):
        EventEnvelope.model_validate(obligation(payload=cash))


def test_payload_given_as_a_model_instance_is_accepted():
    payload = ObligationRecorded.model_validate(obligation()["payload"])
    event = EventEnvelope.model_validate(obligation(payload=payload))
    assert event.payload == payload


def test_every_event_type_has_a_payload_schema():
    from tallyproof_core.events import PAYLOAD_TYPES

    assert set(PAYLOAD_TYPES) == set(EventType)


def test_outlay_period_must_be_a_fiscal_month():
    outlay = obligation(
        event_type="outlay.reported",
        payload={
            "award_key": "CONT_AWD_1",
            "treasury_account": "075-2025/2026-0849-000",
            "fiscal_year": 2025,
            "fiscal_period": 13,
            "cumulative_outlay": "100.00",
            "period_outlay": "100.00",
        },
    )
    with pytest.raises(ValidationError, match="less than or equal to 12"):
        EventEnvelope.model_validate(outlay)
