"""The fake broker behaves like Redpanda for everything the code asks of Kafka.

The same script runs against a real broker and against :class:`FakeBroker`:
produce with keys and headers, assign from a stored offset in the rebalance
callback, consume, seek back, consume again. What each returns must match, so a
test that passes against the fake isn't relying on behavior Kafka doesn't have.
"""

import time
import uuid
from typing import Any

import pytest
from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from testcontainers.community.kafka import RedpandaContainer

from tests.fakes import FakeBroker

pytestmark = pytest.mark.integration
IPV4 = {"broker.address.family": "v4"}
Seen = tuple[str, int, int, bytes | None, bytes | None, list[tuple[str, bytes]] | None]


def script(producer: Any, consumer: Any, topic: str) -> dict[str, Any]:
    """Produce five messages, read from offset 2, seek to 1, read again."""
    errors: list[object] = []
    for n in range(5):
        producer.produce(
            topic,
            value=f"value-{n}".encode(),
            key=f"key-{n % 2}".encode(),
            headers=[("n", str(n).encode())],
            on_delivery=lambda error, message: errors.append(error),
        )
    unconfirmed = producer.flush(10)

    def from_two(c: Any, partitions: list[TopicPartition]) -> None:
        c.assign([TopicPartition(p.topic, p.partition, 2) for p in partitions])

    consumer.subscribe([topic], on_assign=from_two)
    first = read(consumer, 3)
    consumer.seek(TopicPartition(topic, 0, 1))
    second = read(consumer, 4)
    consumer.close()
    return {"errors": errors, "unconfirmed": unconfirmed, "first": first, "second": second}


def read(consumer: Any, count: int) -> list[Seen]:
    seen: list[Seen] = []
    deadline = time.monotonic() + 30
    while len(seen) < count and time.monotonic() < deadline:
        for m in consumer.consume(num_messages=count - len(seen), timeout=0.5):
            if m.error() is None:
                headers = [(k, bytes(v)) for k, v in (m.headers() or [])] or None
                seen.append((m.topic(), m.partition(), m.offset(), m.key(), m.value(), headers))
    return seen


def test_the_fake_broker_matches_redpanda(redpanda: RedpandaContainer) -> None:
    servers = redpanda.get_bootstrap_server()
    topic = f"contract.{uuid.uuid4().hex[:8]}"
    admin = AdminClient({"bootstrap.servers": servers, **IPV4})
    for future in admin.create_topics([NewTopic(topic, 1, 1)]).values():
        future.result(timeout=30)
    real = script(
        Producer({"bootstrap.servers": servers, "acks": "all", **IPV4}),
        Consumer(
            {
                "bootstrap.servers": servers,
                "group.id": f"contract-{topic}",
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
                **IPV4,
            }
        ),
        topic,
    )
    broker = FakeBroker()
    fake = script(broker, broker.consumer(), topic)
    assert real == fake
    assert [m[2] for m in fake["first"]] == [2, 3, 4]
    assert [m[2] for m in fake["second"]] == [1, 2, 3, 4]
