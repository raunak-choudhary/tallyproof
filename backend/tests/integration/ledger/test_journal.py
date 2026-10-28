import pytest
from django.db import DatabaseError, connection, transaction

from apps.ledger.append import append
from apps.ledger.models import JournalLine
from apps.ledger.projections import JournalProjection, catch_up, step
from tests.integration.ledger.test_append import deliveries, event

pytestmark = pytest.mark.django_db


def add(count: int) -> None:
    with transaction.atomic():
        append(deliveries([event() for _ in range(count)]))


def scalar(sql: str) -> object:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchone()[0]


def test_the_journal_balances_and_the_trial_balance_is_zero(migrated):
    add(7)
    assert catch_up(JournalProjection(), batch_size=3) == 7
    assert JournalLine.objects.count() == 14
    assert scalar("SELECT sum(debit) - sum(credit) FROM journal_line") == 0
    assert scalar("SELECT next_leaf_index FROM projection_cursor WHERE name = 'journal'") == 7
    assert step(JournalProjection()) == 0  # nothing new: nothing posted twice
    add(2)
    assert catch_up(JournalProjection()) == 2
    assert JournalLine.objects.count() == 18


def test_the_database_refuses_an_unbalanced_entry(migrated):
    add(1)
    catch_up(JournalProjection())
    line = JournalLine.objects.first()
    assert line is not None
    lonely = JournalLine(
        event=line.event,
        leaf_index=0,
        entry_id="jrn:extra",
        line_number=1,
        account="receipts",
        debit=5,
        credit=0,
    )

    def insert_and_check() -> None:
        with transaction.atomic():
            lonely.save()
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    with pytest.raises(DatabaseError, match="does not balance"):
        insert_and_check()


def test_journal_lines_cannot_be_changed(migrated):
    add(1)
    catch_up(JournalProjection())

    def change() -> None:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE journal_line SET account = 'receipts'")

    with pytest.raises(DatabaseError, match=r"permission denied|append-only"):
        change()
