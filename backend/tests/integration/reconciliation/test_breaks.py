import pytest
from django.db import transaction
from django.test import Client

from apps.ledger.append import Delivery, append
from apps.ledger.models import Outbox
from apps.ledger.projections import catch_up, step
from apps.reconciliation.models import ReconBreak
from apps.reconciliation.projection import ReconciliationProjection
from tallyproof_pipeline.overlay import Anomaly, inject
from tests.unit.core.test_reconciliation import EXPECTED
from tests.unit.pipeline.test_overlay import real_events

pytestmark = pytest.mark.django_db


@pytest.fixture
def overlaid(migrated):
    result = inject(real_events(), seed=42, per_anomaly=3)
    with transaction.atomic():
        append([Delivery(e, "fin.events.raw.v1", 0, i) for i, e in enumerate(result.events)])
    return result


def test_labeled_anomalies_become_breaks_with_their_events(overlaid):
    catch_up(ReconciliationProjection(), batch_size=10)
    stored = {
        (b.break_type, link.event.public_id)
        for b in ReconBreak.objects.all()
        for link in b.events.select_related("event")
    }
    for label in overlaid.labels:
        if label.anomaly in EXPECTED:
            assert (EXPECTED[label.anomaly].value, label.event_id) in stored, label
    assert Outbox.objects.filter(topic="recon.breaks.v1").count() == ReconBreak.objects.count()


def test_a_restarted_projection_rebuilds_its_state(overlaid):
    step(ReconciliationProjection(), batch_size=len(overlaid.events) // 2)
    catch_up(ReconciliationProjection())  # empty state, cursor halfway through the log
    labeled = [x for x in overlaid.labels if x.anomaly == Anomaly.DEOBLIGATION_EXCEEDS_AWARD]
    found = ReconBreak.objects.filter(break_type="deobligation_exceeds_award").count()
    assert found == len(labeled)


def test_breaks_are_served_with_their_events(overlaid):
    catch_up(ReconciliationProjection())
    client = Client(HTTP_HOST="localhost")
    page = client.get("/api/v1/reconciliation/breaks?break_type=deobligation_exceeds_award").json()
    assert page["results"]
    first = page["results"][0]
    assert [e["role"] for e in first["events"]] == ["award", "deobligation"]
    detail = client.get(f"/api/v1/reconciliation/breaks/{first['break_id']}").json()
    assert detail == first
    assert client.get("/api/v1/reconciliation/breaks/brk_nope").status_code == 404
    assert client.get("/api/v1/reconciliation/breaks?break_type=bogus").status_code == 400
