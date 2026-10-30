import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest
from pydantic import ValidationError

from tallyproof_core.events import EventEnvelope, EventType, OutlayReported
from tallyproof_pipeline.gold import conform
from tallyproof_pipeline.overlay import (
    BURST_SIZE,
    BURST_SPACING,
    FALLBACK_TREASURY_ACCOUNT,
    INJECTION_TEXT,
    LATE_BY,
    Anomaly,
    OverlayResult,
    fiscal_period,
    inject,
    write_labels,
)


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
        if e.event_type not in (EventType.OBLIGATION_RECORDED, EventType.OBLIGATION_ADJUSTED):
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


def test_orphan_outlays_name_awards_that_were_never_obligated(result):
    obligated = {
        e.payload.award_key
        for e in result.events
        if e.event_type in (EventType.OBLIGATION_RECORDED, EventType.OBLIGATION_ADJUSTED)
    }
    by_id = {e.event_id: e for e in result.events}
    for label in result.labels:
        if label.anomaly == Anomaly.ORPHAN_OUTLAY:
            event = by_id[label.event_id]
            assert event.event_type is EventType.OUTLAY_REPORTED
            assert event.payload.award_key not in obligated
            assert event.payload.treasury_account == FALLBACK_TREASURY_ACCOUNT


def test_injected_outlays_borrow_a_real_treasury_account_when_one_exists():
    real = real_events()
    source = real[0]
    outlay = EventEnvelope.model_validate(
        {
            **source.model_dump(mode="python"),
            "event_id": source.event_id.replace("evt_0", "evt_2", 1),
            "idempotency_key": "usaspending:outlay:A0:2025-04",
            "event_type": "outlay.reported",
            "payload": {
                "award_key": "CONT_AWD_A0",
                "treasury_account": "089-0222",
                "fiscal_year": 2025,
                "fiscal_period": 7,
                "cumulative_outlay": "10.00",
                "period_outlay": "10.00",
            },
        }
    )
    planned = inject([*real, outlay], seed=42, per_anomaly=2)
    accounts = {
        e.payload.treasury_account for e in planned.events if isinstance(e.payload, OutlayReported)
    }
    assert accounts == {"089-0222"}


def test_a_recipient_burst_is_many_distinct_small_awards_to_one_new_recipient(result):
    by_id = {e.event_id: e for e in result.events}
    real_recipients = {e.account_id for e in result.events if e.event_id not in injected(result)}
    for label in result.labels:
        if label.anomaly != Anomaly.RECIPIENT_BURST:
            continue
        burst = [by_id[label.event_id], *(by_id[i] for i in label.related_event_ids)]
        assert len(burst) == BURST_SIZE
        (recipient,) = {e.account_id for e in burst}
        assert recipient not in real_recipients
        assert len(recipient) == 12
        assert len({e.payload.award_key for e in burst}) == BURST_SIZE
        assert len({e.payload.amount for e in burst}) == BURST_SIZE
        gaps = {b.emitted_at - a.emitted_at for a, b in pairwise(burst)}
        assert gaps == {BURST_SPACING}


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2024, 10, 1), (2025, 1)),
        (date(2025, 9, 30), (2025, 12)),
        (date(2025, 1, 15), (2025, 4)),
    ],
)
def test_fiscal_periods_start_in_october(day, expected):
    assert fiscal_period(day) == expected


def injected(result: OverlayResult) -> set[str]:
    ids: set[str] = set()
    for label in result.labels:
        if label.event_id:
            ids.add(label.event_id)
        if label.anomaly == Anomaly.RECIPIENT_BURST:
            ids.update(label.related_event_ids)
    return ids
