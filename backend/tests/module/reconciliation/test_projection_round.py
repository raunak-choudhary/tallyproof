"""Reconciliation as ``manage.py project`` runs it, beside a projection that fails.

One round steps every projection in its own transaction. A failing projection
must leave nothing half-written and must not stop reconciliation from finding
breaks and announcing them through the outbox.
"""

from collections.abc import Sequence

import pytest
from django.db import DatabaseError, connection, transaction

from apps.ledger.append import Delivery, append
from apps.ledger.models import JournalLine, LedgerEvent, Outbox
from apps.ledger.projections import JournalProjection, run_round
from apps.reconciliation.models import ReconBreak
from apps.reconciliation.projection import ReconciliationProjection
from tallyproof_pipeline.overlay import inject
from tests.unit.pipeline.test_overlay import real_events

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class Broken:
    """Writes a journal line, then fails, as a projection hitting a bad row would."""

    name = "broken"

    def apply(self, events: Sequence[LedgerEvent]) -> None:
        JournalProjection().apply(events[:1])
        raise DatabaseError("constraint violated")


def cursor_of(name: str) -> int | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT next_leaf_index FROM projection_cursor WHERE name = %s", [name])
        row = cursor.fetchone()
    return None if row is None else int(row[0])


def test_a_failing_projection_writes_nothing_and_reconciliation_carries_on(migrated):
    log = inject(real_events(), seed=7, per_anomaly=2)
    with transaction.atomic():
        append([Delivery(e, "fin.events.raw.v1", 0, i) for i, e in enumerate(log.events)])
    total = LedgerEvent.objects.count()  # injected duplicate submissions are refused
    read = 0
    while this_round := run_round([Broken(), ReconciliationProjection()], batch_size=50):
        read += this_round
    assert read == total
    assert cursor_of("reconciliation") == total
    assert cursor_of("broken") in (None, 0)
    assert not JournalLine.objects.exists()  # the failed step's line was rolled back
    assert ReconBreak.objects.exists()
    assert Outbox.objects.filter(topic="recon.breaks.v1").count() == ReconBreak.objects.count()
