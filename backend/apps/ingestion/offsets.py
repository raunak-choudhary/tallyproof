"""Consumer offsets stored in Postgres, fenced by a generation number (ADR-0008).

Offsets are committed in the same transaction as the events they cover, so the
ledger and the read position can never disagree. When a consumer is assigned a
partition it claims it, which bumps the partition's generation. Every later
commit must carry that generation; a consumer that lost the partition in a
rebalance but hasn't noticed yet carries an older one, and its commit (and so
its whole transaction) is refused.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from django.db import connection


class FencedError(RuntimeError):
    """Another consumer has claimed this partition since we did."""

    def __init__(self, topic: str, partition: int, generation: int) -> None:
        """Name the partition that was lost."""
        super().__init__(f"{topic}[{partition}] was claimed by a newer consumer than {generation}")
        self.topic = topic
        self.partition = partition


@dataclass(frozen=True)
class Claim:
    """Where to resume a partition, and the generation that owns it now."""

    next_offset: int
    generation: int


def claim(group: str, topic: str, partition: int) -> Claim:
    """Take ownership of a partition and return where to resume reading it."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO consumer_offset (consumer_group, topic, partition, next_offset, generation)
            VALUES (%s, %s, %s, 0, 1)
            ON CONFLICT (consumer_group, topic, partition) DO UPDATE
              SET generation = consumer_offset.generation + 1, updated_at = now()
            RETURNING next_offset, generation
            """,
            [group, topic, partition],
        )
        next_offset, generation = cursor.fetchone()
    return Claim(next_offset, generation)


def stored(group: str, topic: str, partition: int) -> int:
    """Read where a partition should resume, without claiming it."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT next_offset FROM consumer_offset"
            " WHERE consumer_group = %s AND topic = %s AND partition = %s",
            [group, topic, partition],
        )
        row = cursor.fetchone()
    return int(row[0]) if row else 0


def commit(group: str, positions: Mapping[tuple[str, int], tuple[int, int]]) -> None:
    """Record the next offset to read for each partition, inside the caller's transaction.

    Args:
        group: Consumer group.
        positions: ``(topic, partition) -> (next_offset, generation)``.

    Raises:
        FencedError: If any partition has been claimed by a newer generation.
    """
    with connection.cursor() as cursor:
        for (topic, partition), (next_offset, generation) in positions.items():
            cursor.execute(
                """
                UPDATE consumer_offset
                   SET next_offset = GREATEST(next_offset, %s), updated_at = now()
                 WHERE consumer_group = %s AND topic = %s AND partition = %s AND generation = %s
                """,
                [next_offset, group, topic, partition, generation],
            )
            if cursor.rowcount != 1:
                raise FencedError(topic, partition, generation)
