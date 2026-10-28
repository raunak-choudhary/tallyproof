"""Ledger tables.

``ledger_event`` is the source of truth. Each row stores the exact canonical
bytes that were hashed into the Merkle log; every other column is either derived
from those bytes (and checked against them by the database) or transport
metadata that the proof does not cover.

Rows in ``ledger_event``, ``ledger_batch``, and ``dedupe_rejection`` are never
updated or deleted. The application role has no grant to do so, and triggers
refuse it as a second layer (see the migrations).
"""

from django.db import models
from django.db.models import F, Func, Q
from django.db.models.fields.json import KeyTransform
from django.db.models.functions import Now

from tallyproof_core.events import EventType


class LedgerEvent(models.Model):
    """One accepted event, at its position in the Merkle log."""

    public_id = models.TextField(unique=True)
    leaf_index = models.BigIntegerField(unique=True)
    idempotency_key = models.TextField(unique=True)
    event_type = models.TextField(choices=[(t.value, t.value) for t in EventType])
    account_id = models.TextField()
    occurred_at = models.DateTimeField()
    emitted_at = models.DateTimeField()
    ingested_at = models.DateTimeField(db_default=Now())
    canonical_bytes = models.BinaryField()
    leaf_hash = models.BinaryField()
    payload = models.GeneratedField(
        expression=KeyTransform(
            "payload",
            Func(F("canonical_bytes"), function="ledger_document", output_field=models.JSONField()),
        ),
        output_field=models.JSONField(),
        db_persist=True,
    )
    kafka_topic = models.TextField()
    kafka_partition = models.IntegerField()
    kafka_offset = models.BigIntegerField()
    correlation_id = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ledger_event"
        constraints = [
            models.CheckConstraint(
                condition=Q(leaf_index__gte=0), name="ledger_event_leaf_index_gte_0"
            ),
            models.CheckConstraint(
                condition=Q(public_id__startswith="evt_"), name="ledger_event_public_id_prefix"
            ),
        ]
        indexes = [
            models.Index(fields=["event_type", "occurred_at"], name="ledger_event_type_time"),
            models.Index(fields=["account_id"], name="ledger_event_account"),
        ]

    def __str__(self) -> str:
        return f"{self.public_id} @ {self.leaf_index}"


class LedgerBatch(models.Model):
    """A signed checkpoint closing the leaves ``[start_index, tree_size)``."""

    public_id = models.TextField(unique=True)
    start_index = models.BigIntegerField()
    tree_size = models.BigIntegerField(unique=True)
    root_hash = models.BinaryField()
    checkpoint_note = models.TextField()
    key_id = models.TextField()
    closed_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "ledger_batch"
        constraints = [
            models.CheckConstraint(
                condition=Q(start_index__gte=0) & Q(tree_size__gt=F("start_index")),
                name="ledger_batch_nonempty_range",
            ),
            models.CheckConstraint(
                condition=Q(public_id__startswith="bat_"), name="ledger_batch_public_id_prefix"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.public_id} [{self.start_index}, {self.tree_size})"


class MerkleLogHead(models.Model):
    """The single row holding the next leaf index.

    Leaf indexes come from this row, locked inside the inserting transaction,
    rather than from a sequence: a rolled-back transaction restores the row, so
    indexes stay contiguous. Sequences would leave gaps.
    """

    id = models.SmallIntegerField(primary_key=True, default=1)
    next_leaf_index = models.BigIntegerField(default=0)

    class Meta:
        db_table = "merkle_log_head"
        constraints = [
            models.CheckConstraint(condition=Q(id=1), name="merkle_log_head_single_row"),
            models.CheckConstraint(
                condition=Q(next_leaf_index__gte=0), name="merkle_log_head_index_gte_0"
            ),
        ]

    def __str__(self) -> str:
        return f"next leaf {self.next_leaf_index}"


class ConsumerOffset(models.Model):
    """The next Kafka offset to read, committed in the same transaction as the events.

    ``generation`` fences out a consumer that lost its partition assignment but
    has not noticed yet: its writes carry an older generation and are refused.
    """

    consumer_group = models.TextField()
    topic = models.TextField()
    partition = models.IntegerField()
    next_offset = models.BigIntegerField()
    generation = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "consumer_offset"
        constraints = [
            models.UniqueConstraint(
                fields=["consumer_group", "topic", "partition"], name="consumer_offset_unique"
            ),
            models.CheckConstraint(condition=Q(next_offset__gte=0), name="consumer_offset_gte_0"),
        ]

    def __str__(self) -> str:
        return f"{self.consumer_group} {self.topic}[{self.partition}] -> {self.next_offset}"


class DedupeRejection(models.Model):
    """A delivery refused because its idempotency key was already in the ledger."""

    idempotency_key = models.TextField()
    rejected_event_id = models.TextField()
    kafka_topic = models.TextField()
    kafka_partition = models.IntegerField()
    kafka_offset = models.BigIntegerField()
    bloom_said_seen = models.BooleanField()
    rejected_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "dedupe_rejection"
        indexes = [models.Index(fields=["idempotency_key"], name="dedupe_rejection_key")]

    def __str__(self) -> str:
        return f"duplicate {self.idempotency_key}"


class Outbox(models.Model):
    """A message written with the change that caused it, published later by a relay."""

    topic = models.TextField()
    key = models.TextField()
    payload = models.JSONField()
    created_at = models.DateTimeField(db_default=Now())
    published_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "outbox"
        indexes = [
            models.Index(
                fields=["id"], condition=Q(published_at__isnull=True), name="outbox_unpublished"
            )
        ]

    def __str__(self) -> str:
        return f"{self.topic} {self.key}"
