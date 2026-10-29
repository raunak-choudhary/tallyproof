"""The question and answer endpoints over the evaluation dataset, with a fake model."""

import json
from functools import partial

import pytest
from django.core.cache import cache
from django.db import transaction
from django.test import Client
from psycopg import errors

from apps.analyst import api
from apps.analyst.llm import FakeClient, LLMRequest
from apps.analyst.service import answer_question
from apps.ledger.append import Delivery, append
from apps.ledger.models import LedgerBatch, LedgerEvent
from evals.dataset import OUT_DIR
from tallyproof_pipeline.gold import read_events
from tests.integration.analyst.conftest import AsAnalyst

pytestmark = pytest.mark.django_db

HHS = "Department of Health and Human Services"
SPEC = {
    "shape": "aggregate",
    "entity": "obligations",
    "metric": "sum_amount",
    "filters": [{"field": "awarding_agency", "op": "eq", "value": HHS}],
}


def scripted(request: LLMRequest) -> str:
    if request.prompt_version == "router.v2":
        return json.dumps({"category": "numeric_aggregate", "spec": SPEC})
    return json.dumps({"answer": "HHS obligated {{s1}} across {{s2}} actions [[c1]]."})


@pytest.fixture
def client(as_analyst: None, monkeypatch: pytest.MonkeyPatch) -> Client:
    events = list(read_events(OUT_DIR / "events.jsonl.gz"))
    with transaction.atomic():
        append([Delivery(e, "fin.events.raw.v1", 0, i) for i, e in enumerate(events)])
    cache.clear()  # throttle history from other tests
    fake = FakeClient(scripted)
    monkeypatch.setattr(
        api,
        "answer_question",
        partial(answer_question, executor=AsAnalyst(), client=fake, search=lambda q, k: []),
    )
    return Client(HTTP_HOST="localhost")


def seal() -> int:
    size = LedgerEvent.objects.count()
    LedgerBatch.objects.create(
        public_id="bat_TEST", start_index=0, tree_size=size, root_hash=b"\0" * 32,
        checkpoint_note="test", key_id="test",
    )  # fmt: skip
    return size


def test_nothing_is_answered_before_a_checkpoint_exists(client):
    reply = client.post(
        "/api/v1/queries", {"question": "How much did HHS obligate?"}, "application/json"
    )
    assert reply.status_code == 201
    assert reply.json()["refusal"]["code"] == "no_checkpoint"


def test_a_question_is_answered_with_values_citations_and_proof_urls(client):
    size = seal()
    reply = client.post(
        "/api/v1/queries", {"question": "How much did HHS obligate?"}, "application/json"
    )
    assert reply.status_code == 201
    body = reply.json()
    assert body["status"] == "answered"
    assert body["text"] == "HHS obligated $17,049,347.67 across 29 actions [[c1]]."
    assert body["checkpoint_tree_size"] == size
    assert body["filter_words"].endswith(f"awarding agency is {HHS}")
    assert body["assurance"] == "filter_shown"
    (citation,) = body["citations"]
    assert len(citation["events"]) == 29
    first = citation["events"][0]
    assert first["proof_url"] == f"/api/v1/events/{first['event_id']}/proof?tree_size={size}"
    assert body["slots"][0] == {
        "label": "s1", "kind": "money", "value": "17049347.67", "display": "$17,049,347.67",
        "meaning": f"total of obligations and modifications where awarding agency is {HHS}",
        "citation": "c1",
    }  # fmt: skip
    assert "verified" not in json.dumps(body)  # proofs, never verdicts
    assert reply["Location"] == f"/api/v1/answers/{body['answer_id']}"
    assert client.get(reply["Location"]).json() == body


def test_refusals_explain_themselves(client):
    seal()
    body = client.post(
        "/api/v1/queries", {"question": "What is the CEO's home address?"}, "application/json"
    ).json()
    assert (body["status"], body["refusal"]["code"]) == ("refused", "personal_data")
    assert body["refusal"]["message"]


def test_bad_requests_and_unknown_answers(client):
    assert client.post("/api/v1/queries", {"question": "x"}, "application/json").status_code == 400
    assert client.post("/api/v1/queries", {}, "application/json").status_code == 400
    assert client.get("/api/v1/answers/ans_nope").status_code == 404


def test_questions_have_their_own_rate_limit(client, monkeypatch):
    monkeypatch.setattr(api.QueryRateThrottle, "THROTTLE_RATES", {"queries": "2/min"})
    seal()
    codes = [
        client.post(
            "/api/v1/queries", {"question": "Tell me a joke"}, "application/json"
        ).status_code
        for _ in range(3)
    ]
    assert codes == [201, 201, 429]


def test_stored_answers_can_not_be_changed(migrated):
    with migrated.connect("app") as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute("UPDATE analyst_answer SET text = ''")


def test_a_total_over_the_cap_keeps_the_full_total_and_labels_its_sample(client, monkeypatch):
    from apps.analyst.pipeline import Models

    seal()
    capped = Models("m", "m", 400, 10)
    monkeypatch.setattr(
        api,
        "answer_question",
        partial(
            answer_question,
            executor=AsAnalyst(),
            client=FakeClient(scripted),
            search=lambda q, k: [],
            chosen=capped,
        ),
    )
    body = client.post(
        "/api/v1/queries", {"question": "How much did HHS obligate?"}, "application/json"
    ).json()
    assert body["status"] == "answered"
    assert body["text"] == "HHS obligated $17,049,347.67 across 29 actions [[c1]]."
    (citation,) = body["citations"]
    assert citation["sample_of"] == 29
    assert len(citation["events"]) == 10
    assert citation["meaning"] == "the first 10 of the 29 records counted, in log order"
    leaves = [e["leaf_index"] for e in citation["events"]]
    assert leaves == sorted(leaves)
