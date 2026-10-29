import json

import pytest

from tallyproof_core.events import EventEnvelope
from tallyproof_pipeline.stream import (
    ReplayError,
    interleave,
    partition_key,
    publish,
    read_invalid,
)
from tests.fakes import FakeBroker, FrozenClock
from tests.unit.pipeline.test_overlay import cash_event, real_events


def invalid_record(source: EventEnvelope) -> dict[str, object]:
    record: dict[str, object] = json.loads(source.model_dump_json())
    record["payload"] = {**source.payload.model_dump(mode="json"), "amount": 1250.5}  # float money
    return record


def test_events_are_keyed_by_award_and_cash_by_account():
    event = real_events(1)[0]
    assert (
        partition_key(event) == json.loads(event.model_dump_json())["payload"]["award_key"].encode()
    )
    cash = cash_event()
    assert partition_key(cash) == b"treasury-operating-cash"


def test_invalid_records_are_merged_in_at_their_arrival_time():
    events = real_events(10)
    bad = invalid_record(events[4])
    stream = list(interleave(events, [bad]))
    assert [m.valid for m in stream].index(False) == 4
    assert len(stream) == 11
    late = invalid_record(events[9]) | {"emitted_at": "2030-01-01T00:00:00Z"}
    assert not list(interleave(events, [late]))[-1].valid


def test_published_values_round_trip_through_the_consumer_schema():
    producer = FakeBroker()
    events = real_events(5)
    summary = publish(interleave(events, []), producer, "raw", rate_per_sec=1000)
    assert summary.events == 5
    decoded = [
        EventEnvelope.model_validate_json(m.value() or b"") for m in producer.messages("raw")
    ]
    assert [e.leaf_hash() for e in decoded] == [e.leaf_hash() for e in events]


def test_publishing_is_paced_to_the_rate_and_stops_at_the_limit():
    clock = FrozenClock(0.0)
    producer = FakeBroker()
    summary = publish(
        interleave(real_events(40), []),
        producer,
        "raw",
        10,
        limit=20,
        clock=clock,
        sleep=clock.sleep,
    )
    assert summary.events == len(producer.messages("raw")) == 20
    assert sum(clock.slept) == pytest.approx(1.9)  # 20 messages at 10 per second


def test_rejected_or_unconfirmed_messages_fail_the_replay():
    with pytest.raises(ReplayError, match="rejected"):
        publish(interleave(real_events(2), []), FakeBroker(reject=True), "raw", 1000)
    with pytest.raises(ReplayError, match="unconfirmed"):
        publish(interleave(real_events(2), []), FakeBroker(unconfirmed=1), "raw", 1000)


def test_missing_invalid_file_means_no_invalid_records(tmp_path):
    assert read_invalid(tmp_path / "absent.jsonl.gz") == []
