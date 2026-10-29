"""An in-memory Kafka broker that speaks the parts of confluent-kafka the code uses.

One :class:`FakeBroker` holds topics as lists of messages. It is the producer
(``produce``, ``poll``, ``flush``) and hands out consumers (``subscribe``,
``consume``, ``assign``, ``seek``, ``assignment``, ``close``) that read from it.
A contract test (``tests/integration/test_fake_broker_contract.py``) runs the same
script against Redpanda and against this fake and compares what each returns.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from confluent_kafka import OFFSET_BEGINNING, KafkaError, TopicPartition

Header = tuple[str, str | bytes | None]


@dataclass(frozen=True)
class FakeError:
    """A broker error on a message, as ``Message.error()`` returns it."""

    _code: int = KafkaError._PARTITION_EOF

    def code(self) -> int:
        return self._code


@dataclass
class FakeMessage:
    """One message, read the way ``confluent_kafka.Message`` is read."""

    _topic: str
    _value: bytes | None
    _offset: int = 0
    _partition: int = 0
    _key: bytes | None = None
    _headers: list[Header] | None = None
    _error: FakeError | None = None

    def topic(self) -> str:
        return self._topic

    def value(self) -> bytes | None:
        return self._value

    def offset(self) -> int:
        return self._offset

    def partition(self) -> int:
        return self._partition

    def key(self) -> bytes | None:
        return self._key

    def headers(self) -> list[Header] | None:
        return self._headers

    def error(self) -> FakeError | None:
        return self._error


DeliveryCallback = Callable[[Any, FakeMessage], None]


@dataclass
class FakeBroker:
    """Topics in memory. Set ``reject`` to fail every delivery, ``unconfirmed`` to
    make ``flush`` report messages still waiting."""

    reject: bool = False
    unconfirmed: int = 0
    topics: dict[str, list[FakeMessage]] = field(default_factory=dict)

    def produce(
        self,
        topic: str,
        value: bytes | None = None,
        key: bytes | None = None,
        headers: list[Header] | None = None,
        on_delivery: DeliveryCallback | None = None,
        **_: Any,
    ) -> None:
        log = self.topics.setdefault(topic, [])
        message = FakeMessage(topic, value, len(log), 0, key, headers)
        if not self.reject:
            log.append(message)
        if on_delivery is not None:
            on_delivery("delivery rejected" if self.reject else None, message)

    def poll(self, timeout: float = 0) -> int:
        return 0

    def flush(self, timeout: float = 0) -> int:
        return self.unconfirmed

    def messages(self, topic: str) -> list[FakeMessage]:
        """Everything produced to ``topic``, in order."""
        return list(self.topics.get(topic, []))

    def inject(self, message: FakeMessage) -> None:
        """Put a message, such as one carrying an error, straight onto its topic."""
        self.topics.setdefault(message.topic(), []).append(message)

    def consumer(self) -> "FakeConsumer":
        """A consumer reading this broker's topics."""
        return FakeConsumer(self)


@dataclass
class FakeConsumer:
    """A consumer with partition 0 of each subscribed topic assigned to it."""

    broker: FakeBroker
    positions: dict[tuple[str, int], int] = field(default_factory=dict)
    closed: bool = False

    def subscribe(
        self,
        topics: Sequence[str],
        on_assign: Callable[["FakeConsumer", list[TopicPartition]], None] | None = None,
        on_revoke: Callable[["FakeConsumer", list[TopicPartition]], None] | None = None,
        on_lost: Callable[["FakeConsumer", list[TopicPartition]], None] | None = None,
    ) -> None:
        partitions = [TopicPartition(t, 0, OFFSET_BEGINNING) for t in topics]
        if on_assign is not None:
            on_assign(self, partitions)
        else:
            self.assign(partitions)

    def assign(self, partitions: Sequence[TopicPartition]) -> None:
        for p in partitions:
            self.positions[(p.topic, p.partition)] = max(p.offset, 0)

    def assignment(self) -> list[TopicPartition]:
        return [TopicPartition(t, p, o) for (t, p), o in self.positions.items()]

    def seek(self, partition: TopicPartition) -> None:
        self.positions[(partition.topic, partition.partition)] = partition.offset

    def consume(self, num_messages: int = 1, timeout: float = -1) -> list[FakeMessage]:
        batch: list[FakeMessage] = []
        for (topic, partition), position in self.positions.items():
            waiting = self.broker.topics.get(topic, [])[position:]
            taken = waiting[: num_messages - len(batch)]
            batch.extend(taken)
            self.positions[(topic, partition)] = position + len(taken)
            if len(batch) >= num_messages:
                break
        return batch

    def close(self) -> None:
        self.closed = True
