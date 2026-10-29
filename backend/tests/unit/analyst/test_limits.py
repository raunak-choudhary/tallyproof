import threading

import pytest
from django.core.cache import cache

from apps.analyst import limits
from apps.analyst.llm import FakeClient, LLMRequest, Message


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


def test_spending_adds_up_per_address_and_stops_at_the_budget(monkeypatch):
    class Settings:
        analyst_per_ip_daily_tokens = 100

    monkeypatch.setattr(limits, "app_settings", lambda: Settings)
    limits.spend("10.0.0.1", 60)
    assert not limits.over_budget("10.0.0.1")
    limits.spend("10.0.0.1", 40)
    assert limits.tokens_spent("10.0.0.1") == 100
    assert limits.over_budget("10.0.0.1")
    assert not limits.over_budget("10.0.0.2")
    limits.spend("10.0.0.2", 0)
    assert limits.tokens_spent("10.0.0.2") == 0


def test_answering_slots_refuse_at_once_when_full(monkeypatch):
    one = threading.BoundedSemaphore(1)
    monkeypatch.setattr(limits, "_slots", lambda: one)
    with limits.answering_slot(), pytest.raises(limits.BusyError), limits.answering_slot():
        pass
    with limits.answering_slot():  # released again
        pass


def test_the_counting_client_adds_up_tokens():
    counting = limits.CountingClient(FakeClient(["a reply", "another"]))
    request = LLMRequest("m", "v1", (Message("user", "a question of some length"),), 50)
    replies = [counting.complete(request), counting.complete(request)]
    assert counting.tokens == sum(r.input_tokens + r.output_tokens for r in replies)
