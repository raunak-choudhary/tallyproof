"""Run the reconciliation rules as a projection of the log.

Breaks, their event links, and an outbox message announcing each break are
written in the same transaction that advances the projection's cursor. The
rules keep running totals in memory, so on startup the projection replays the
log up to its cursor to rebuild them, without writing anything.
"""

from collections.abc import Sequence
from datetime import timedelta

from apps.ledger.models import LedgerEvent, Outbox
from apps.ledger.projections import envelope_of
from apps.reconciliation.models import BreakEvent, ReconBreak
from config.env import app_settings
from tallyproof_core.ids import new_id
from tallyproof_core.reconciliation import Reconciler

WARM_UP_CHUNK = 5000


class ReconciliationProjection:
    """Finds breaks as events are appended."""

    name = "reconciliation"

    def __init__(self) -> None:
        """Configure the rules from settings; state is rebuilt lazily."""
        env = app_settings()
        self.engine = Reconciler(
            late_after=timedelta(hours=env.recon_late_arrival_watermark_hours),
            tolerance=env.recon_amount_tolerance,
        )
        self.topic = env.kafka_topic_recon_breaks
        self.position = 0

    def _warm_up(self, until: int) -> None:
        while self.position < until:
            rows = LedgerEvent.objects.filter(
                leaf_index__gte=self.position,
                leaf_index__lt=min(until, self.position + WARM_UP_CHUNK),
            ).order_by("leaf_index")
            for row in rows:
                self.engine.apply(envelope_of(row))
                self.position = row.leaf_index + 1

    def apply(self, events: Sequence[LedgerEvent]) -> None:
        """Run the rules over the next events and record any breaks."""
        if events and self.position != events[0].leaf_index:
            self.engine = Reconciler(
                late_after=self.engine.late_after, tolerance=self.engine.tolerance
            )
            self.position = 0
            self._warm_up(events[0].leaf_index)
        by_public_id = {row.public_id: row for row in events}
        for row in events:
            for found in self.engine.apply(envelope_of(row)):
                involved = {
                    event_id: by_public_id.get(event_id)
                    or LedgerEvent.objects.get(public_id=event_id)
                    for event_id, _ in found.events
                }
                recon_break, created = ReconBreak.objects.get_or_create(
                    dedupe_key=found.dedupe_key,
                    defaults={
                        "public_id": new_id("brk"),
                        "break_type": found.break_type.value,
                        "award_key": found.award_key,
                        "amount_delta": found.amount_delta,
                        "detail": found.detail,
                        "leaf_index": row.leaf_index,
                    },
                )
                if not created:
                    continue
                BreakEvent.objects.bulk_create(
                    BreakEvent(recon_break=recon_break, event=involved[event_id], role=role)
                    for event_id, role in found.events
                )
                Outbox.objects.create(
                    topic=self.topic,
                    key=row.account_id,
                    payload={
                        "break_id": recon_break.public_id,
                        "break_type": found.break_type.value,
                        "award_key": found.award_key,
                        "amount_delta": None
                        if found.amount_delta is None
                        else str(found.amount_delta),
                        "event_ids": [event_id for event_id, _ in found.events],
                        "leaf_index": row.leaf_index,
                    },
                )
            self.position = row.leaf_index + 1
