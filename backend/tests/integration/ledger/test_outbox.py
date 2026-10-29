import pytest
from django.db import transaction

from apps.ledger.append import append
from apps.ledger.models import Outbox
from apps.ledger.outbox import OutboxLag, RelayError, relay_batch
from apps.ledger.projections import AppendedProjection, catch_up
from tests.fakes import FakeBroker
from tests.integration.ledger.test_append import deliveries, event

pytestmark = pytest.mark.django_db


def appended(count: int) -> None:
    with transaction.atomic():
        append(deliveries([event() for _ in range(count)]))
    catch_up(AppendedProjection("ledger.appended.v1"))


def test_each_event_is_announced_once_and_marked_published(migrated):
    appended(5)
    producer = FakeBroker()
    assert relay_batch(producer, limit=3) == 3
    assert relay_batch(producer, limit=3) == 2
    assert relay_batch(producer) == 0
    ids = []
    for message in (m for messages in producer.topics.values() for m in messages):
        outbox_id = dict(message.headers() or [])["outbox-id"]
        assert isinstance(outbox_id, bytes)
        ids.append(int(outbox_id))
    assert ids == sorted(ids)
    assert len(set(ids)) == 5
    assert not Outbox.objects.filter(published_at__isnull=True).exists()


def test_a_rejected_batch_stays_unpublished_for_the_next_attempt(migrated):
    appended(2)
    with pytest.raises(RelayError):
        relay_batch(FakeBroker(reject=True))
    assert Outbox.objects.filter(published_at__isnull=True).count() == 2
    assert relay_batch(FakeBroker()) == 2


def test_lag_counts_unpublished_messages_and_the_oldest_ones_age(migrated):
    from apps.ledger.outbox import outbox_lag

    assert outbox_lag() == OutboxLag(pending=0, oldest_seconds=None)
    appended(3)
    lag = outbox_lag()
    assert lag.pending == 3
    assert lag.oldest_seconds is not None
    assert lag.oldest_seconds >= 0
    relay_batch(FakeBroker())
    assert outbox_lag().pending == 0
