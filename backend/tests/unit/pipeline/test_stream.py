import json
from dataclasses import dataclass, field

import pytest

from tallyproof_core.events import EventEnvelope
from tallyproof_pipeline.stream import (
    ReplayError,
    interleave,
    partition_key,
    publish,
    read_invalid,
)
from tests.unit.pipeline.test_overlay import cash_event, real_events


@dataclass
class FakeProducer:
    unconfirmed: int = 0
    reject: bool = False
    sent: list[tuple[str, bytes, bytes]] = field(default_factory=list)

    def produce(self, topic, *, value, key, on_delivery):  # keywords, like confluent-kafka
        self.sent.append((topic, key, value))
        on_delivery("broker said no" if self.reject else None, None)

    def poll(self, timeout):
        return 0

    def flush(self, timeout):
        return self.unconfirmed


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds


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
    producer = FakeProducer()
    events = real_events(5)
    summary = publish(interleave(events, []), producer, "raw", rate_per_sec=1000)
    assert summary.events == 5
    decoded = [EventEnvelope.model_validate_json(value) for _, _, value in producer.sent]
    assert [e.leaf_hash() for e in decoded] == [e.leaf_hash() for e in events]


def test_publishing_is_paced_to_the_rate_and_stops_at_the_limit():
    clock = FakeClock()
    producer = FakeProducer()
    summary = publish(
        interleave(real_events(40), []),
        producer,
        "raw",
        10,
        limit=20,
        clock=clock,
        sleep=clock.sleep,
    )
    assert summary.events == len(producer.sent) == 20
    assert clock.slept == pytest.approx(1.9)  # 20 messages at 10 per second


def test_rejected_or_unconfirmed_messages_fail_the_replay():
    with pytest.raises(ReplayError, match="rejected"):
        publish(interleave(real_events(2), []), FakeProducer(reject=True), "raw", 1000)
    with pytest.raises(ReplayError, match="unconfirmed"):
        publish(interleave(real_events(2), []), FakeProducer(unconfirmed=1), "raw", 1000)


def test_missing_invalid_file_means_no_invalid_records(tmp_path):
    assert read_invalid(tmp_path / "absent.jsonl.gz") == []
