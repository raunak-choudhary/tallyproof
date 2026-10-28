import random
from datetime import UTC, datetime

import pytest
from django.db import connection, connections, transaction

from apps.ledger.append import AppendError, Delivery, append
from tallyproof_core.events import EventEnvelope
from tallyproof_core.ids import new_id

pytestmark = pytest.mark.django_db


def event(key: str | None = None, event_id: str | None = None) -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "event_id": event_id or new_id("evt"),
            "idempotency_key": key or f"test:{new_id('src')}",
            "event_type": "obligation.recorded",
            "occurred_at": datetime(2025, 1, 2, tzinfo=UTC),
            "emitted_at": datetime(2025, 1, 3, tzinfo=UTC),
            "account_id": "ZQGGHJH74DW7",
            "correlation_id": "c-1",
            "payload": {
                "award_key": "CONT_AWD_A1",
                "piid": "PIID1",
                "awarding_agency": "Department of Energy",
                "amount": "10.00",
                "action_date": "2025-01-02",
            },
        }
    )


def deliveries(events: list[EventEnvelope], start_offset: int = 0) -> list[Delivery]:
    return [Delivery(e, "fin.events.raw.v1", 0, start_offset + i) for i, e in enumerate(events)]


def leaf_indexes() -> list[int]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT leaf_index FROM ledger_event ORDER BY leaf_index")
        return [row[0] for row in cursor.fetchall()]


def head() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT next_leaf_index FROM merkle_log_head")
        return int(cursor.fetchone()[0])


def test_events_get_consecutive_leaf_indexes_in_arrival_order(migrated):
    events = [event() for _ in range(5)]
    with transaction.atomic():
        result = append(deliveries(events))
    assert result.appended == [(e.event_id, i) for i, e in enumerate(events)]
    assert result.tree_size == head() == 5


def test_duplicates_in_the_ledger_and_within_a_batch_are_refused_and_logged(migrated):
    first = event(key="test:k1")
    with transaction.atomic():
        append(deliveries([first]))
    redelivered = event(key="test:k1")  # same key, new event ID: a duplicate delivery
    twice = event(key="test:k2")
    same_id = event(event_id=twice.event_id)  # same event ID under another key
    batch = [redelivered, twice, event(key="test:k2"), same_id]
    with transaction.atomic():
        result = append(
            [
                Delivery(e, "fin.events.raw.v1", 0, 10 + i, bloom_said_seen=True)
                for i, e in enumerate(batch)
            ]
        )
    assert [event_id for event_id, _ in result.appended] == [twice.event_id]
    assert len(result.duplicates) == 3
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*), bool_and(bloom_said_seen) FROM dedupe_rejection")
        assert cursor.fetchone() == (3, True)
    assert leaf_indexes() == [0, 1]


def test_random_rollbacks_never_leave_a_gap(migrated):
    rng = random.Random(20261027)
    committed = 0
    for _ in range(40):
        size = rng.randint(0, 6)
        roll_back = rng.random() < 0.4
        try:
            with transaction.atomic():
                append(deliveries([event() for _ in range(size)]))
                if roll_back:
                    raise RuntimeError("simulated crash before commit")
        except RuntimeError:
            continue
        committed += size
    assert leaf_indexes() == list(range(committed))
    assert head() == committed


def test_append_refuses_to_run_outside_a_transaction(migrated, monkeypatch):
    # The db fixture wraps every test in a transaction, so pretend it doesn't.
    monkeypatch.setattr(connections["default"], "in_atomic_block", False)
    with pytest.raises(AppendError, match="atomic"):
        append(deliveries([event()]))


def test_an_empty_batch_changes_nothing(migrated):
    with transaction.atomic():
        assert append([]).tree_size == 0
