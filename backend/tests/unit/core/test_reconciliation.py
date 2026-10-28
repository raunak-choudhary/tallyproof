from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tallyproof_core.events import EventEnvelope
from tallyproof_core.ids import new_id
from tallyproof_core.reconciliation import Break, BreakType, Reconciler
from tallyproof_pipeline.overlay import Anomaly, inject
from tests.unit.pipeline.test_overlay import real_events

EXPECTED = {
    Anomaly.DEOBLIGATION_EXCEEDS_AWARD: BreakType.DEOBLIGATION_EXCEEDS_AWARD,
    Anomaly.DUPLICATE_AWARD_SEMANTIC: BreakType.POSSIBLE_DUPLICATE_AWARD,
    Anomaly.LATE_ARRIVAL: BreakType.LATE_AFTER_CLOSE,
}


def run(events: list[EventEnvelope]) -> list[Break]:
    engine = Reconciler()
    return [b for e in events for b in engine.apply(e)]


@pytest.fixture(scope="module")
def overlaid():
    return inject(real_events(), seed=42, per_anomaly=3)


def test_every_labeled_anomaly_is_caught_by_its_rule(overlaid):
    found = {(b.break_type, b.trigger_event_id) for b in run(overlaid.events)}
    for label in overlaid.labels:
        if label.anomaly in EXPECTED:
            assert (EXPECTED[label.anomaly], label.event_id) in found, label


def test_untouched_real_events_raise_no_breaks():
    assert run(real_events()) == []


def test_the_same_log_gives_the_same_breaks(overlaid):
    first, second = run(overlaid.events), run(overlaid.events)
    assert first == second
    assert len({b.dedupe_key for b in first}) == len(first)


def outlay(award: str, cumulative: str, period: int = 1) -> EventEnvelope:
    now = datetime(2025, 3, 1, tzinfo=UTC)
    return EventEnvelope.model_validate(
        {
            "event_id": new_id("evt"),
            "idempotency_key": f"test:outlay:{award}:{period}",
            "event_type": "outlay.reported",
            "occurred_at": now,
            "emitted_at": now + timedelta(hours=1),
            "account_id": "ZQGGHJH74DW7",
            "correlation_id": "c",
            "payload": {
                "award_key": award,
                "treasury_account": "089-0222",
                "fiscal_year": 2025,
                "fiscal_period": period,
                "cumulative_outlay": cumulative,
                "period_outlay": cumulative,
            },
        }
    )


def test_outlays_without_or_above_obligations_are_breaks():
    obligation = real_events(1)[0]  # 1,000.00 obligated on CONT_AWD_A0
    award = obligation.payload.model_dump()["award_key"]
    breaks = run(
        [
            outlay("CONT_AWD_NEVER", "50.00"),
            obligation,
            outlay(award, "900.00"),
            outlay(award, "1500.00", 2),
        ]
    )
    assert [b.break_type for b in breaks] == [
        BreakType.ORPHAN_OUTLAY,
        BreakType.OUTLAY_EXCEEDS_OBLIGATION,
    ]
    assert breaks[1].amount_delta == Decimal("500.00")
    assert breaks[1].events[0] == (obligation.event_id, "award")


def test_a_break_lists_each_event_once_even_when_it_opened_the_award():
    # Real data: an award's first event in the ledger can itself be a de-obligation.
    adjustment = next(e for e in real_events() if e.event_type.value == "obligation.adjusted")
    payload = {**adjustment.payload.model_dump(mode="json"), "amount": "-50.00"}
    first = adjustment.model_copy(
        update={"payload": type(adjustment.payload).model_validate(payload)}
    )
    (found,) = Reconciler().apply(first)
    assert found.break_type is BreakType.DEOBLIGATION_EXCEEDS_AWARD
    assert found.events == ((first.event_id, "award"),)
