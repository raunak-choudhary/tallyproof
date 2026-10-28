import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tallyproof_core.events import EventEnvelope, EventType
from tallyproof_pipeline.gold import conform
from tallyproof_pipeline.overlay import INJECTION_TEXT, LATE_BY, Anomaly, inject, write_labels


def real_events(count: int = 40) -> list[EventEnvelope]:
    events = []
    for i in range(count):
        day = date(2025, 1, 1) + timedelta(days=i)
        events.append(
            conform(
                {
                    "contract_transaction_unique_key": f"T{i}",
                    "contract_award_unique_key": f"CONT_AWD_A{i % 10}",
                    "award_id_piid": f"PIID{i % 10}",
                    "modification_number": "0" if i < 10 else f"P{i:05d}",
                    "federal_action_obligation": Decimal("1000.00") * (i + 1),
                    "action_date": day,
                    "last_modified_date": datetime.combine(day, datetime.min.time()),
                    "awarding_agency_name": "Department of Energy",
                    "recipient_uei": f"UEI{i % 5:09d}",
                    "transaction_description": "SERVICES",
                },
                seed=1,
            )
        )
    return events


def cash_event() -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "event_id": real_events(1)[0].event_id.replace("evt_0", "evt_1", 1),
            "idempotency_key": "fiscaldata:dts:2025-01-02:deposit:taxes",
            "event_type": "cash.movement",
            "occurred_at": "2025-01-02T00:00:00Z",
            "emitted_at": "2025-01-03T00:00:00Z",
            "account_id": "treasury-operating-cash",
            "correlation_id": "cash-1",
            "payload": {
                "record_date": "2025-01-02",
                "account": "Treasury General Account",
                "direction": "deposit",
                "category": "Taxes - Withheld Individual/FICA",
                "amount": "12345",
            },
        }
    )


@pytest.fixture(scope="module")
def result():
    # Cash movements share the stream; the overlay must leave them alone.
    return inject([*real_events(), cash_event()], seed=42, per_anomaly=3)


def test_every_anomaly_type_is_injected_the_requested_number_of_times(result):
    counts = {a: sum(1 for label in result.labels if label.anomaly == a) for a in Anomaly}
    assert all(count == 3 for count in counts.values())


def test_labels_point_at_injected_events_and_their_real_sources(result):
    ids = {e.event_id for e in result.events}
    for label in result.labels:
        if label.anomaly != Anomaly.SCHEMA_INVALID:
            assert label.event_id in ids
        assert all(source in ids for source in label.related_event_ids)


def test_events_do_not_reveal_that_they_were_injected(result):
    text = " ".join(e.model_dump_json() for e in result.events).lower()
    for word in ("overlay", "anomaly", "injected", "synthetic", "label"):
        assert word not in text


def test_duplicate_delivery_reuses_the_idempotency_key_with_a_new_event_id(result):
    by_id = {e.event_id: e for e in result.events}
    for label in result.labels:
        if label.anomaly == Anomaly.DUPLICATE_DELIVERY:
            copy, source = by_id[label.event_id], by_id[label.related_event_ids[0]]
            assert copy.idempotency_key == source.idempotency_key
            assert copy.event_id != source.event_id


def test_deobligation_exceeds_everything_obligated_on_the_award(result):
    totals: dict[str, Decimal] = {}
    for e in result.events:
        if e.event_type is EventType.CASH_MOVEMENT:
            continue
        key = e.payload.award_key
        totals[key] = totals.get(key, Decimal(0)) + Decimal(e.payload.amount)
    by_id = {e.event_id: e for e in result.events}
    for label in result.labels:
        if label.anomaly == Anomaly.DEOBLIGATION_EXCEEDS_AWARD:
            assert totals[by_id[label.event_id].payload.award_key] < 0


def test_late_arrivals_are_reported_long_after_they_happened(result):
    by_id = {e.event_id: e for e in result.events}
    for label in result.labels:
        if label.anomaly == Anomaly.LATE_ARRIVAL:
            event = by_id[label.event_id]
            assert event.emitted_at - event.occurred_at == LATE_BY


def test_injection_text_is_carried_in_a_description(result):
    by_id = {e.event_id: e for e in result.events}
    for label in result.labels:
        if label.anomaly == Anomaly.INJECTION_DESCRIPTION:
            assert by_id[label.event_id].payload.description == INJECTION_TEXT


def test_invalid_records_fail_validation(result):
    assert len(result.invalid_records) == 3
    for record in result.invalid_records:
        with pytest.raises(ValidationError):
            EventEnvelope.model_validate(record)


def test_output_is_in_emission_order(result):
    times = [e.emitted_at for e in result.events]
    assert times == sorted(times)


def test_same_seed_gives_identical_output_and_different_seed_differs():
    first = inject(real_events(), seed=42, per_anomaly=3)
    second = inject(real_events(), seed=42, per_anomaly=3)
    other = inject(real_events(), seed=7, per_anomaly=3)
    assert [e.leaf_hash() for e in first.events] == [e.leaf_hash() for e in second.events]
    assert [e.leaf_hash() for e in first.events] != [e.leaf_hash() for e in other.events]


def test_overlay_needs_a_recorded_obligation():
    adjustments = [e for e in real_events() if e.event_type is EventType.OBLIGATION_ADJUSTED]
    with pytest.raises(ValueError, match=r"obligation\.recorded"):
        inject(adjustments, seed=1, per_anomaly=1)


def test_labels_are_written_as_sorted_json_lines(result, tmp_path):
    path = tmp_path / "gold" / "labels.jsonl"
    write_labels(result.labels, path)
    lines = path.read_text().splitlines()
    assert len(lines) == len(result.labels)
    assert list(json.loads(lines[0])) == sorted(json.loads(lines[0]))
