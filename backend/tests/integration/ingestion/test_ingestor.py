import base64
import json

import pytest
from django.db import connection

from apps.ingestion import offsets
from apps.ingestion.consumer import DeadLetterError, Ingestor
from apps.ingestion.dedupe import PartitionFilters
from tests.fakes import FakeBroker, FakeMessage
from tests.integration.ledger.test_append import event

pytestmark = pytest.mark.django_db
TOPIC = "fin.events.raw.v1"
DLQ = "fin.events.dlq.v1"


def message(value: bytes, offset: int, partition: int = 0) -> FakeMessage:
    return FakeMessage(TOPIC, value, offset, partition, b"award")


def make_ingestor(sink: FakeBroker | None = None, group: str = "ingest-test") -> Ingestor:
    ingestor = Ingestor(group, DLQ, sink or FakeBroker(), PartitionFilters(10_000, 0.001))
    ingestor.assign(TOPIC, 0)
    return ingestor


def valid(offset: int, key: str | None = None) -> FakeMessage:
    return message(event(key=key).model_dump_json().encode(), offset)


def stored_offset(group: str = "ingest-test") -> int:
    return offsets.stored(group, TOPIC, 0)


def test_valid_events_are_appended_and_the_offset_moves_past_the_batch(migrated):
    ingestor = make_ingestor()
    outcome = ingestor.process([valid(0), valid(1), valid(2)])
    assert (outcome.appended, outcome.duplicates, outcome.dead_lettered) == (3, 0, 0)
    assert outcome.tree_size == 3
    assert stored_offset() == 3


def test_invalid_records_go_to_the_dead_letter_topic_without_echoing_values(migrated):
    sink = FakeBroker()
    ingestor = make_ingestor(sink)
    bad = json.loads(event().model_dump_json())
    bad["payload"]["amount"] = "12.5e3"
    messages = [message(b"not json", 0), message(json.dumps(bad).encode(), 1), valid(2)]
    outcome = ingestor.process(messages)
    assert (outcome.appended, outcome.dead_lettered) == (1, 2)
    assert stored_offset() == 3
    assert set(sink.topics) == {DLQ}
    record = json.loads(sink.messages(DLQ)[1].value() or b"")
    assert record["source"] == {"topic": TOPIC, "partition": 0, "offset": 1}
    assert record["problems"][0]["field"].startswith("payload")
    assert "12.5e3" not in json.dumps(record["problems"])
    assert base64.b64decode(record["raw_base64"]) == json.dumps(bad).encode()


def test_nothing_is_committed_when_dead_letters_are_not_confirmed(migrated):
    ingestor = make_ingestor(FakeBroker(unconfirmed=1))
    with pytest.raises(DeadLetterError):
        ingestor.process([message(b"{}", 0), valid(1)])
    assert stored_offset() == 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM ledger_event")
        assert cursor.fetchone() == (0,)


def test_a_redelivered_batch_is_refused_as_duplicates(migrated):
    ingestor = make_ingestor()
    batch = [valid(0, key="test:a"), valid(1, key="test:b")]
    ingestor.process(batch)
    again = ingestor.process([valid(0, key="test:a"), valid(1, key="test:b")])
    assert (again.appended, again.duplicates) == (0, 2)
    assert ingestor.filters.stats.false_positives == 0
    assert stored_offset() == 2


def test_a_consumer_that_lost_its_partition_cannot_commit(migrated):
    old = make_ingestor()
    new = make_ingestor()  # a rebalance gave the partition to someone else
    with pytest.raises(offsets.FencedError) as raised:
        old.process([valid(0)])
    assert (raised.value.topic, raised.value.partition) == (TOPIC, 0)
    assert new.process([valid(0)]).appended == 1
    assert stored_offset() == 1


def test_rewind_returns_the_stored_offset_without_reclaiming(migrated):
    ingestor = make_ingestor()
    ingestor.process([valid(0), valid(1)])
    generation = ingestor.generations[(TOPIC, 0)]
    assert ingestor.rewind(TOPIC, 0) == 2
    assert ingestor.process([valid(2)]).appended == 1  # still the owner: not fenced
    assert ingestor.generations[(TOPIC, 0)] == generation


def test_assignment_rebuilds_the_filter_from_the_ledger(migrated):
    first = make_ingestor(group="g1")
    first.process([valid(0, key="test:x")])
    second = make_ingestor(group="g2")
    assert second.filters.check_and_add(TOPIC, 0, "test:x") is True
    assert second.filters.check_and_add(TOPIC, 0, "test:never-seen") is False


def test_messages_for_partitions_not_owned_are_skipped(migrated):
    ingestor = make_ingestor()
    outcome = ingestor.process([message(b"{}", 0, partition=7), valid(0)])
    assert (outcome.appended, outcome.dead_lettered) == (1, 0)
    ingestor.revoke(TOPIC, 0)
    assert TOPIC not in {t for t, _ in ingestor.generations}
