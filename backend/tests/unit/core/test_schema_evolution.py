"""Registry version 2 adds an optional payload field; events without it keep their bytes."""

from datetime import UTC, datetime
from typing import Any

from tallyproof_core.events import EventEnvelope
from tallyproof_core.ids import new_id
from tallyproof_core.journal import entry_for


def obligation(**payload: Any) -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "event_id": new_id("evt"),
            "idempotency_key": "test:schema:1",
            "event_type": "obligation.recorded",
            "occurred_at": datetime(2025, 1, 2, tzinfo=UTC),
            "emitted_at": datetime(2025, 1, 3, tzinfo=UTC),
            "account_id": "ZQGGHJH74DW7",
            "correlation_id": "c-1",
            "payload": {
                "award_key": "CONT_AWD_A1",
                "piid": "PIID1",
                "awarding_agency": "Department of Energy",
                "amount": "1250.00",
                "action_date": "2025-01-02",
                **payload,
            },
        }
    )


def test_an_event_without_the_new_field_hashes_as_it_always_did() -> None:
    text = obligation().canonical_bytes().decode()
    assert '"schema_version":1' in text
    assert "recipient_parent_uei" not in text


def test_an_event_with_the_new_field_carries_it() -> None:
    event = obligation(recipient_parent_uei="PARENT123456")
    assert '"recipient_parent_uei":"PARENT123456"' in event.canonical_bytes().decode()


def test_the_journal_is_the_same_with_or_without_the_new_field() -> None:
    old = entry_for(obligation())
    new = entry_for(obligation(recipient_parent_uei="PARENT123456"))
    assert [(line.account, line.debit, line.credit) for line in old] == [
        (line.account, line.debit, line.credit) for line in new
    ]
