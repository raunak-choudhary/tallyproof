import pytest

from apps.ingestion.control_totals import reconcile_range
from tests.integration.ingestion.test_ingestor import TOPIC, make_ingestor, valid

pytestmark = pytest.mark.django_db


def test_every_message_is_accounted_for_and_amounts_match(migrated):
    ingestor = make_ingestor()
    batch = [valid(0, key="test:a"), valid(1, key="test:b"), valid(2, key="test:a")]
    batch.append(type(batch[0])(b"not json", 3))
    ingestor.process(batch)
    messages = {m.offset(): m.value() for m in batch}
    report = reconcile_range(TOPIC, 0, messages, 0, 4)
    assert report.ok, report.problems
    assert (report.appended, report.duplicates, report.invalid) == (2, 1, 1)


def test_a_message_the_ledger_never_saw_is_reported(migrated):
    ingestor = make_ingestor()
    first = valid(0)
    ingestor.process([first])
    missing = valid(1)
    report = reconcile_range(TOPIC, 0, {0: first.value(), 1: missing.value()}, 0, 2)
    assert not report.ok
    assert any("neither appended nor refused" in p for p in report.problems)


def test_a_stored_row_that_differs_from_its_message_is_reported(migrated):
    ingestor = make_ingestor()
    stored = valid(0)
    ingestor.process([stored])
    impostor = valid(0)  # a different event claiming the same offset
    report = reconcile_range(TOPIC, 0, {0: impostor.value()}, 0, 1)
    assert any("does not match its message" in p for p in report.problems)
