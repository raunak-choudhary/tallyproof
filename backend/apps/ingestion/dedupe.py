"""Per-partition Bloom filters in front of the database's duplicate check.

The database's unique constraints decide what is a duplicate; the filter only
predicts it. Its prediction is recorded with each delivery so the pipeline can
report how often it was right: a "seen" prediction for a key the database then
accepts is a false positive, and the measured rate is compared with the target.
A "new" prediction is never wrong, which is what Bloom filters guarantee.

Filters are rebuilt from the ledger whenever a partition is assigned, because
another consumer may have appended to it in the meantime.
"""

from dataclasses import dataclass

from django.db import connection

from tallyproof_core.bloom import BloomFilter


@dataclass
class BloomStats:
    """Running counts for the filter's measured accuracy."""

    checked: int = 0
    predicted_seen: int = 0
    false_positives: int = 0

    @property
    def false_positive_rate(self) -> float:
        """False positives as a share of keys the database accepted as new."""
        new = self.checked - (self.predicted_seen - self.false_positives)
        return self.false_positives / new if new else 0.0


class PartitionFilters:
    """One Bloom filter per (topic, partition)."""

    def __init__(self, expected_items: int, target_fpr: float) -> None:
        """Size every filter for ``expected_items`` keys at ``target_fpr``."""
        self._expected_items = expected_items
        self._target_fpr = target_fpr
        self._filters: dict[tuple[str, int], BloomFilter] = {}
        self.stats = BloomStats()

    def rebuild(self, topic: str, partition: int) -> int:
        """Load every key already in the ledger from this partition. Returns the count."""
        bloom = BloomFilter.for_capacity(self._expected_items, self._target_fpr)
        loaded = 0
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT idempotency_key FROM ledger_event"
                " WHERE kafka_topic = %s AND kafka_partition = %s",
                [topic, partition],
            )
            for (key,) in cursor:
                bloom.add(key.encode())
                loaded += 1
        self._filters[(topic, partition)] = bloom
        return loaded

    def drop(self, topic: str, partition: int) -> None:
        """Forget a partition this consumer no longer owns."""
        self._filters.pop((topic, partition), None)

    def check_and_add(self, topic: str, partition: int, key: str) -> bool:
        """Predict whether ``key`` was seen before, then remember it."""
        bloom = self._filters.get((topic, partition))
        if bloom is None:
            raise KeyError(f"no filter for {topic}[{partition}]; was it assigned?")
        encoded = key.encode()
        seen = bloom.might_contain(encoded)
        bloom.add(encoded)
        self.stats.checked += 1
        self.stats.predicted_seen += seen
        return seen

    def record_outcome(self, predicted_seen: bool, was_duplicate: bool) -> None:
        """Count a prediction the database contradicted."""
        if predicted_seen and not was_duplicate:
            self.stats.false_positives += 1
