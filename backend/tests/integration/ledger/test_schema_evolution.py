"""Events with and without the version 2 field in one log: both appended, journal unchanged."""

import pytest
from django.db import transaction

from apps.ledger.append import append
from apps.ledger.models import JournalLine
from apps.ledger.projections import JournalProjection, catch_up
from tests.integration.conftest import Database
from tests.integration.ledger.test_append import deliveries
from tests.unit.core.test_schema_evolution import obligation

pytestmark = pytest.mark.django_db


def test_old_and_new_events_flow_together_and_post_the_same_journal(migrated: Database) -> None:
    old = obligation().model_copy(update={"idempotency_key": "test:v1"})
    new = obligation(recipient_parent_uei="PARENT123456").model_copy(
        update={"idempotency_key": "test:v2"}
    )
    with transaction.atomic():
        result = append(deliveries([old, new]))
    assert [event_id for event_id, _ in result.appended] == [old.event_id, new.event_id]
    assert catch_up(JournalProjection()) == 2

    def lines(event_id: str) -> list[tuple[str, object, object]]:
        rows = JournalLine.objects.filter(event__public_id=event_id).order_by("line_number")
        return [(r.account, r.debit, r.credit) for r in rows]

    assert lines(old.event_id) == lines(new.event_id)
    assert lines(old.event_id)
