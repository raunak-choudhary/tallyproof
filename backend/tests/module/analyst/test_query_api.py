"""The analyst over HTTP: a question in, a cited answer or a typed refusal out.

The real router, compiler, composer, verifier, serializer, view, throttle, and
answering slots run here. The model is scripted, the database executor is fake,
and the answer is built in memory instead of saved, so no service is needed.
"""

import json
import threading
from decimal import Decimal
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.analyst import api, limits, service
from apps.analyst.models import AnalystAnswer
from apps.analyst.pipeline import ask
from tests.fakes import FakeLLM
from tests.unit.analyst.test_pipeline import MODELS, SUM_SPEC, Database, model, search

TREE_SIZE = 50
URL = "/api/v1/queries"
COMPOSED = "State obligated {{s1}} over {{s2}} actions [[c1]]."


@pytest.fixture(autouse=True)
def fresh_cache() -> Any:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def addresses(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """Answer through the real pipeline with fakes, and record whose budget each charged."""
    seen: list[str | None] = []

    def answer_question(question: str, *, address: str | None = None) -> AnalystAnswer:
        seen.append(address)
        llm = FakeLLM(model(**{
            "router.v2": json.dumps({"category": "numeric_aggregate", "spec": SUM_SPEC}),
            "composer.v4": json.dumps({"answer": COMPOSED}),
        }))  # fmt: skip
        db = Database(
            value=[(Decimal("500.00"), 2)],
            evidence=[("evt_a", 1, Decimal(250)), ("evt_b", 2, Decimal(250))],
        )
        result = ask(
            question, client=llm, executor=db, search=search([]), models=MODELS,
            agencies=["Department of State"], tree_size=TREE_SIZE,
        )  # fmt: skip
        evidence = result.evidence
        return AnalystAnswer(
            public_id="ans_test", question=result.question, status=result.status,
            category=result.category or "", refusal=result.refusal or "", text=result.text,
            tree_size=TREE_SIZE, assurance=evidence.assurance if evidence else "",
            filter_words=evidence.filter_words if evidence else "",
            body=service._body(result, MODELS), created_at=timezone.now(),
        )  # fmt: skip

    monkeypatch.setattr(api, "answer_question", answer_question)
    return seen


def test_a_question_comes_back_with_values_citations_and_proof_links(addresses):
    response = Client().post(URL, {"question": "How much did State obligate?"}, "application/json")
    assert response.status_code == 201
    assert response["Location"] == "/api/v1/answers/ans_test"
    body = response.json()
    assert body["status"] == "answered"
    assert body["text"] == "State obligated $500.00 over 2 actions [[c1]]."
    assert [s["display"] for s in body["slots"]] == ["$500.00", "2"]
    events = body["citations"][0]["events"]
    assert [e["event_id"] for e in events] == ["evt_a", "evt_b"]
    assert events[0]["proof_url"] == f"/api/v1/events/evt_a/proof?tree_size={TREE_SIZE}"
    assert body["checkpoint_tree_size"] == TREE_SIZE
    assert "SELECT" not in response.content.decode()


def test_a_verdict_question_is_refused_with_a_reason(addresses):
    response = Client().post(
        URL, {"question": "Is this vendor committing fraud?"}, "application/json"
    )
    assert response.status_code == 201
    refusal = response.json()["refusal"]
    assert refusal["code"] == "judgment_beyond_data"
    assert refusal["message"]


def test_a_malformed_question_is_a_problem_response(addresses):
    response = Client().post(URL, {"question": "x"}, "application/json")
    assert response.status_code == 400
    assert response.json()["type"].endswith("invalid-question")
    assert addresses == []


def test_a_busy_analyst_says_when_to_try_again(addresses, monkeypatch):
    none_free = threading.BoundedSemaphore(1)
    none_free.acquire()
    monkeypatch.setattr(limits, "_slots", lambda: none_free)
    response = Client().post(URL, {"question": "How much did State obligate?"}, "application/json")
    assert response.status_code == 503
    assert response["Retry-After"] == str(limits.RETRY_AFTER_SECONDS)
    assert addresses == []


def test_rotating_ipv6_addresses_share_one_limit_and_one_budget(addresses, monkeypatch):
    monkeypatch.setattr(api.QueryRateThrottle, "THROTTLE_RATES", {"queries": "2/min"})
    codes = [
        Client(REMOTE_ADDR=f"2001:db8:1:2::{n}")
        .post(URL, {"question": "How much did State obligate?"}, "application/json")
        .status_code
        for n in range(1, 4)
    ]
    assert codes == [201, 201, 429]
    assert addresses == ["2001:db8:1:2::/64", "2001:db8:1:2::/64"]
