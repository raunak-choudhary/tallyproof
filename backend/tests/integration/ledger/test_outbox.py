from dataclasses import dataclass, field

import pytest
from django.db import transaction

from apps.ledger.append import append
from apps.ledger.models import Outbox
from apps.ledger.outbox import RelayError, relay_batch
from apps.ledger.projections import AppendedProjection, catch_up
from tests.integration.ledger.test_append import deliveries, event

pytestmark = pytest.mark.django_db


@dataclass
class FakeProducer:
    reject: bool = False
    sent: list[tuple[str, bytes, list[tuple[str, str | bytes | None]]]] = field(
        default_factory=list
    )

    def produce(self, topic, *, value, key, headers, on_delivery):
        self.sent.append((topic, value, headers))
        on_delivery("rejected" if self.reject else None, None)

    def flush(self, timeout):
        return 0


def appended(count: int) -> None:
    with transaction.atomic():
        append(deliveries([event() for _ in range(count)]))
    catch_up(AppendedProjection("ledger.appended.v1"))


def test_each_event_is_announced_once_and_marked_published(migrated):
    appended(5)
    producer = FakeProducer()
    assert relay_batch(producer, limit=3) == 3
    assert relay_batch(producer, limit=3) == 2
    assert relay_batch(producer) == 0
    ids = []
    for _, _, headers in producer.sent:
        outbox_id = dict(headers)["outbox-id"]
        assert isinstance(outbox_id, bytes)
        ids.append(int(outbox_id))
    assert ids == sorted(ids)
    assert len(set(ids)) == 5
    assert not Outbox.objects.filter(published_at__isnull=True).exists()


def test_a_rejected_batch_stays_unpublished_for_the_next_attempt(migrated):
    appended(2)
    with pytest.raises(RelayError):
        relay_batch(FakeProducer(reject=True))
    assert Outbox.objects.filter(published_at__isnull=True).count() == 2
    assert relay_batch(FakeProducer()) == 2
