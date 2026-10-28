"""The ingestion loop: Kafka in, validated events appended to the ledger, offsets fenced.

For each batch, in order:

1. Parse and validate every message. Invalid ones go to the dead-letter topic,
   and the producer is flushed before anything is committed, so a rejected
   record can't be lost.
2. Predict duplicates with the partition's Bloom filter.
3. In one transaction: append the valid events, record duplicates, and move each
   partition's stored offset past the batch, refusing if another consumer has
   claimed a partition since (see :mod:`apps.ingestion.offsets`).

If anything fails before the commit, nothing is committed and the batch is read
again from the stored offsets. Duplicates from that retry are refused by the
database, which is what makes processing effectively once.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from confluent_kafka import Consumer, KafkaError, Producer, TopicPartition
from django.db import transaction
from pydantic import ValidationError

from apps.ingestion import dead_letter, offsets
from apps.ingestion.dedupe import PartitionFilters
from apps.ledger.append import Delivery, append
from tallyproof_core.events import EventEnvelope

log = logging.getLogger(__name__)


class Message(Protocol):
    """The parts of a Kafka message the consumer uses."""

    def topic(self) -> str | None: ...  # noqa: D102
    def partition(self) -> int | None: ...  # noqa: D102
    def offset(self) -> int | None: ...  # noqa: D102
    def key(self) -> bytes | None: ...  # noqa: D102
    def value(self) -> bytes | None: ...  # noqa: D102


class DeadLetterSink(Protocol):
    """Where invalid records go. A confluent-kafka ``Producer`` satisfies this."""

    def produce(self, topic: str, value: bytes, key: bytes | None = None) -> None: ...  # noqa: D102
    def flush(self, timeout: float) -> int: ...  # noqa: D102


class DeadLetterError(RuntimeError):
    """Dead-letter records weren't confirmed by the broker, so the batch isn't committed."""


@dataclass
class BatchOutcome:
    """Counts for one processed batch."""

    appended: int = 0
    duplicates: int = 0
    dead_lettered: int = 0
    tree_size: int = 0


@dataclass
class Totals:
    """Counts since the consumer started."""

    batches: int = 0
    appended: int = 0
    duplicates: int = 0
    dead_lettered: int = 0
    by_partition: dict[tuple[str, int], int] = field(default_factory=dict)


class Ingestor:
    """Processes batches for the partitions this consumer currently owns."""

    def __init__(
        self,
        group: str,
        dead_letter_topic: str,
        sink: DeadLetterSink,
        filters: PartitionFilters,
        flush_timeout: float = 10.0,
    ) -> None:
        """Create an ingestor; partitions are added through :meth:`assign`."""
        self.group = group
        self.dead_letter_topic = dead_letter_topic
        self.sink = sink
        self.filters = filters
        self.flush_timeout = flush_timeout
        self.generations: dict[tuple[str, int], int] = {}
        self.totals = Totals()

    def assign(self, topic: str, partition: int) -> int:
        """Claim a partition, rebuild its filter, and return the offset to resume from."""
        with transaction.atomic():
            claimed = offsets.claim(self.group, topic, partition)
        self.generations[(topic, partition)] = claimed.generation
        loaded = self.filters.rebuild(topic, partition)
        log.info(
            "assigned %s[%d] at offset %d, generation %d, %d keys in filter",
            topic,
            partition,
            claimed.next_offset,
            claimed.generation,
            loaded,
        )
        return claimed.next_offset

    def rewind(self, topic: str, partition: int) -> int:
        """After a failed batch: return the stored offset and rebuild the filter.

        The filter saw keys from the batch that was rolled back, so it is rebuilt
        from the ledger. The partition is not claimed again: that would fence out
        whichever consumer owns it now.
        """
        self.filters.rebuild(topic, partition)
        return offsets.stored(self.group, topic, partition)

    def revoke(self, topic: str, partition: int) -> None:
        """Stop tracking a partition this consumer no longer owns."""
        self.generations.pop((topic, partition), None)
        self.filters.drop(topic, partition)

    def process(self, messages: Sequence[Message]) -> BatchOutcome:
        """Validate, dead-letter, deduplicate, append, and commit one batch."""
        deliveries: list[Delivery] = []
        positions: dict[tuple[str, int], tuple[int, int]] = {}
        dead = 0
        for message in messages:
            topic, partition, offset = message.topic(), message.partition(), message.offset()
            if topic is None or partition is None or offset is None:
                continue
            where = (topic, partition)
            if where not in self.generations:
                continue  # revoked mid-batch; the new owner will read it
            next_offset = max(offset + 1, positions.get(where, (0, 0))[0])
            positions[where] = (next_offset, self.generations[where])
            raw = message.value()
            try:
                event = EventEnvelope.model_validate_json(raw or b"")
            except (ValidationError, ValueError) as error:
                self.sink.produce(
                    self.dead_letter_topic,
                    dead_letter.envelope(error, topic, partition, offset, raw),
                    key=message.key(),
                )
                dead += 1
                continue
            seen = self.filters.check_and_add(topic, partition, event.idempotency_key)
            deliveries.append(Delivery(event, topic, partition, offset, bloom_said_seen=seen))

        if dead and self.sink.flush(self.flush_timeout) > 0:
            raise DeadLetterError("dead-letter records were not confirmed; retrying the batch")

        with transaction.atomic():
            result = append(deliveries)
            offsets.commit(self.group, positions)

        duplicate_ids = {id(d) for d in result.duplicates}
        for delivery in deliveries:
            self.filters.record_outcome(delivery.bloom_said_seen, id(delivery) in duplicate_ids)
        outcome = BatchOutcome(len(result.appended), len(result.duplicates), dead, result.tree_size)
        self._count(outcome, deliveries)
        return outcome

    def _count(self, outcome: BatchOutcome, deliveries: Sequence[Delivery]) -> None:
        totals = self.totals
        totals.batches += 1
        totals.appended += outcome.appended
        totals.duplicates += outcome.duplicates
        totals.dead_lettered += outcome.dead_lettered
        for d in deliveries:
            where = (d.topic, d.partition)
            totals.by_partition[where] = totals.by_partition.get(where, 0) + 1


def run(
    ingestor: Ingestor,
    consumer: Consumer,
    topic: str,
    max_batch: int,
    should_stop: Callable[[], bool],
    report_every: int = 50,
) -> None:
    """Consume until ``should_stop`` returns true, then close cleanly."""

    def on_assign(c: Consumer, partitions: list[TopicPartition]) -> None:
        for p in partitions:
            p.offset = ingestor.assign(p.topic, p.partition)
        c.assign(partitions)

    def on_revoke(c: Consumer, partitions: list[TopicPartition]) -> None:
        for p in partitions:
            ingestor.revoke(p.topic, p.partition)

    consumer.subscribe([topic], on_assign=on_assign, on_revoke=on_revoke, on_lost=on_revoke)
    try:
        while not should_stop():
            batch = consumer.consume(num_messages=max_batch, timeout=1.0)
            good = []
            for message in batch:
                error = message.error()
                if error is None:
                    good.append(message)
                elif error.code() != KafkaError._PARTITION_EOF:
                    log.warning("broker error: %s", error)
            if not good:
                continue
            try:
                ingestor.process(good)
            except (offsets.FencedError, DeadLetterError) as error:
                log.warning("batch not committed: %s", error)
                if isinstance(error, offsets.FencedError):
                    # Someone else owns it now; stop until the rebalance catches up.
                    ingestor.revoke(error.topic, error.partition)
                # Re-read the rest from the stored offsets; the database refuses duplicates.
                for p in consumer.assignment():
                    if (p.topic, p.partition) in ingestor.generations:
                        resume = ingestor.rewind(p.topic, p.partition)
                        consumer.seek(TopicPartition(p.topic, p.partition, resume))
                continue
            if ingestor.totals.batches % report_every == 0:
                stats = ingestor.filters.stats
                log.info(
                    "appended %d, duplicates %d, dead-lettered %d, bloom fpr %.5f over %d keys",
                    ingestor.totals.appended,
                    ingestor.totals.duplicates,
                    ingestor.totals.dead_lettered,
                    stats.false_positive_rate,
                    stats.checked,
                )
    finally:
        consumer.close()


def producer_for_dead_letters(bootstrap_servers: str) -> Producer:
    """A producer that waits for every replica to confirm each dead-letter record."""
    return Producer(
        {"bootstrap.servers": bootstrap_servers, "acks": "all", "enable.idempotence": True}
    )
