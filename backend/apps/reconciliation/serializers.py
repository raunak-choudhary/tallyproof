"""Response shapes for the reconciliation API."""

from rest_framework import serializers

from apps.reconciliation.models import ReconBreak


class BreakSerializer(serializers.ModelSerializer[ReconBreak]):
    """A break and the events involved, each provable through the events API."""

    break_id = serializers.CharField(source="public_id")
    events = serializers.SerializerMethodField()

    class Meta:
        model = ReconBreak
        fields = [
            "break_id",
            "break_type",
            "award_key",
            "amount_delta",
            "detail",
            "leaf_index",
            "detected_at",
            "events",
        ]

    def get_events(self, recon_break: ReconBreak) -> list[dict[str, str]]:
        """The events behind the break, with their roles."""
        return [
            {"event_id": link.event.public_id, "role": link.role}
            for link in recon_break.events.select_related("event").order_by("id")
        ]
