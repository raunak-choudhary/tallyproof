import pytest

from apps.ledger.derived import journal_drift, rebuild
from apps.ledger.models import JournalLine
from apps.ledger.projections import JournalProjection, catch_up
from tests.integration.ledger.test_journal import add

pytestmark = pytest.mark.django_db


def test_a_freshly_projected_journal_has_no_drift(migrated):
    add(5)
    catch_up(JournalProjection())
    assert journal_drift() == []


def test_drift_is_found_when_a_stored_entry_disagrees(migrated):
    add(3)
    catch_up(JournalProjection())
    line = JournalLine.objects.order_by("leaf_index").first()
    assert line is not None
    extra = {"event": line.event, "leaf_index": line.leaf_index, "entry_id": "jrn:extra"}
    JournalLine.objects.bulk_create(  # balanced, so the database accepts it; the rules wouldn't
        [
            JournalLine(**extra, line_number=1, account="receipts", debit=1, credit=0),
            JournalLine(**extra, line_number=2, account="disbursements", debit=0, credit=1),
        ]
    )
    assert journal_drift()[0].startswith(f"leaf {line.leaf_index}")


def test_only_the_owner_may_rebuild(migrated):
    with pytest.raises(PermissionError, match="owner"):
        rebuild("journal")
