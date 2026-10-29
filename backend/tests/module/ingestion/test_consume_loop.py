"""The ingestion app's consume loop, fed by a fake broker, writing to a real ledger.

``run`` is the loop ``manage.py ingest`` runs: it subscribes, assigns partitions
from the offsets stored in Postgres, appends good events, dead-letters bad ones,
and closes the consumer. Only Kafka is faked.
"""

import json
from collections.abc import Callable
from typing import cast

import pytest
from confluent_kafka import Consumer, KafkaError
from django.db import connection

from apps.ingestion import offsets
from apps.ingestion.consumer import Ingestor, run
from apps.ingestion.dedupe import PartitionFilters
from tests.fakes import FakeBroker, FakeError, FakeMessage
from tests.integration.ledger.test_append import event

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
RAW, DLQ, GROUP = "fin.events.raw.v1", "fin.events.dlq.v1", "ingest-module"


def rounds(n: int) -> Callable[[], bool]:
    """A should_stop that lets the loop run ``n`` rounds."""
    left = iter(range(n))
    return lambda: next(left, None) is None


def ledger_size() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM ledger_event")
        (count,) = cursor.fetchone() or (0,)
    return int(count)


def ingest(broker: FakeBroker, n: int = 3) -> Ingestor:
    ingestor = Ingestor(GROUP, DLQ, broker, PartitionFilters(10_000, 0.001))
    consumer = broker.consumer()
    # The contract test shows FakeConsumer behaves like confluent's Consumer here.
    run(ingestor, cast("Consumer", consumer), RAW, max_batch=2, should_stop=rounds(n))
    assert consumer.closed
    return ingestor


def test_good_events_are_appended_bad_ones_dead_lettered_and_offsets_stored(migrated):
    broker = FakeBroker()
    for _ in range(3):
        broker.produce(RAW, value=event().model_dump_json().encode(), key=b"award")
    broker.produce(RAW, value=b"not json", key=b"award")
    broker.inject(FakeMessage(RAW, None, 99, _error=FakeError(KafkaError._PARTITION_EOF)))
    broker.inject(FakeMessage(RAW, None, 99, _error=FakeError(KafkaError._TRANSPORT)))
    ingestor = ingest(broker)
    assert (ingestor.totals.appended, ingestor.totals.dead_lettered) == (3, 1)
    assert ledger_size() == 3
    assert offsets.stored(GROUP, RAW, 0) == 4
    (dead,) = broker.messages(DLQ)
    assert json.loads(dead.value() or b"")["source"]["offset"] == 3


def test_a_restart_resumes_from_the_stored_offset_without_duplicates(migrated):
    broker = FakeBroker()
    for _ in range(4):
        broker.produce(RAW, value=event().model_dump_json().encode(), key=b"award")
    ingest(broker)
    assert ledger_size() == 4
    broker.produce(RAW, value=event().model_dump_json().encode(), key=b"award")
    again = ingest(broker)
    assert again.totals.appended == 1
    assert ledger_size() == 5
    assert offsets.stored(GROUP, RAW, 0) == 5


def test_unconfirmed_dead_letters_leave_the_batch_for_the_next_attempt(migrated):
    broker = FakeBroker(unconfirmed=1)
    broker.produce(RAW, value=b"not json", key=b"award")
    broker.produce(RAW, value=event().model_dump_json().encode(), key=b"award")
    ingest(broker, n=2)
    assert ledger_size() == 0
    assert offsets.stored(GROUP, RAW, 0) == 0
    broker.unconfirmed = 0
    ingest(broker)
    assert ledger_size() == 1
    assert offsets.stored(GROUP, RAW, 0) == 2
