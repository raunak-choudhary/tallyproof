"""Response shapes for the ledger API."""

from rest_framework import serializers

from apps.ledger.models import LedgerBatch, LedgerEvent


class EventSerializer(serializers.ModelSerializer[LedgerEvent]):
    """One ledger event, with the exact bytes its leaf hash covers."""

    event_id = serializers.CharField(source="public_id")
    canonical = serializers.SerializerMethodField(
        help_text="The canonical JSON whose leaf hash is in the log. Hash it yourself."
    )
    leaf_hash_hex = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEvent
        fields = [
            "event_id",
            "leaf_index",
            "event_type",
            "account_id",
            "occurred_at",
            "ingested_at",
            "canonical",
            "leaf_hash_hex",
        ]

    def get_canonical(self, event: LedgerEvent) -> str:
        """The stored canonical bytes, as text."""
        return bytes(event.canonical_bytes).decode("utf-8")

    def get_leaf_hash_hex(self, event: LedgerEvent) -> str:
        """The stored leaf hash, hex encoded."""
        return bytes(event.leaf_hash).hex()


class CheckpointSerializer(serializers.ModelSerializer[LedgerBatch]):
    """A signed checkpoint and the range of leaves its batch added."""

    batch_id = serializers.CharField(source="public_id")
    root_hash_hex = serializers.SerializerMethodField()
    note = serializers.CharField(source="checkpoint_note")

    class Meta:
        model = LedgerBatch
        fields = [
            "batch_id",
            "start_index",
            "tree_size",
            "root_hash_hex",
            "note",
            "key_id",
            "closed_at",
        ]

    def get_root_hash_hex(self, batch: LedgerBatch) -> str:
        """The signed root, hex encoded."""
        return bytes(batch.root_hash).hex()


class InclusionProofSerializer(serializers.Serializer[dict[str, object]]):
    """Everything needed to check one event against one signed checkpoint."""

    event_id = serializers.CharField()
    leaf_index = serializers.IntegerField()
    tree_size = serializers.IntegerField()
    leaf_hash_hex = serializers.CharField()
    audit_path_hex = serializers.ListField(child=serializers.CharField())
    checkpoint_note = serializers.CharField()


class ConsistencyProofSerializer(serializers.Serializer[dict[str, object]]):
    """Proof that the first signed tree is a prefix of the second."""

    first_size = serializers.IntegerField()
    second_size = serializers.IntegerField()
    proof_hex = serializers.ListField(child=serializers.CharField())
    first_note = serializers.CharField()
    second_note = serializers.CharField()


class LogKeySerializer(serializers.Serializer[dict[str, object]]):
    """The public key checkpoints are signed with."""

    origin = serializers.CharField()
    verifier_key = serializers.CharField()
