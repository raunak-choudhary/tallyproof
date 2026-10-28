"""Reconciliation breaks: places where related events don't agree.

Breaks are derived data, like the journal, and are append-only. Each break
lists the events involved, so an answer about a break can cite and prove them.
"""

from django.db import models
from django.db.models.functions import Now

from apps.ledger.models import LedgerEvent


class ReconBreak(models.Model):
    """One detected break."""

    public_id = models.TextField(unique=True)
    dedupe_key = models.TextField(unique=True)
    break_type = models.TextField()
    award_key = models.TextField(blank=True, default="")
    amount_delta = models.DecimalField(max_digits=19, decimal_places=4, null=True)
    detail = models.TextField()
    leaf_index = models.BigIntegerField()
    detected_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "recon_break"
        indexes = [models.Index(fields=["break_type", "leaf_index"], name="recon_break_type")]

    def __str__(self) -> str:
        return f"{self.public_id} {self.break_type}"


class BreakEvent(models.Model):
    """An event involved in a break, and its role there."""

    recon_break = models.ForeignKey(ReconBreak, on_delete=models.PROTECT, related_name="events")
    event = models.ForeignKey(LedgerEvent, on_delete=models.PROTECT, related_name="breaks")
    role = models.TextField()

    class Meta:
        db_table = "break_event"
        constraints = [
            models.UniqueConstraint(fields=["recon_break", "event"], name="break_event_unique")
        ]

    def __str__(self) -> str:
        return f"{self.recon_break_id} {self.role}"
