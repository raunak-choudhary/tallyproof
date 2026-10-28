"""Router rules and the model fallback. Phrasings here are not from the held-out set."""

import json

import pytest

from apps.analyst.llm import FakeClient
from apps.analyst.router import PROMPT_VERSION, Route, by_rules, route

AGENCIES = ["Department of Energy", "Department of State"]


def ask(question: str, reply: str = "{}") -> tuple[Route, FakeClient]:
    fake = FakeClient([reply])
    return (
        route(question, fake, model="m", agencies=AGENCIES, max_tokens=300),
        fake,
    )


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        ("What is the phone number of the vendor's CEO?", "personal_data"),
        ("Give me the salary of the contracting officer", "personal_data"),
        ("How much will Energy spend next quarter?", "forecast"),
        ("Predict obligations for the coming year", "forecast"),
        ("Is this vendor guilty of overbilling?", "judgment_beyond_data"),
        ("Which awards look like kickbacks?", "judgment_beyond_data"),
        ("Tell me a joke about budgets", "out_of_scope"),
    ],
)
def test_refusals_are_decided_by_rules(question, reason):
    decided = by_rules(question)
    assert decided is not None
    assert (decided.category, decided.refusal_reason, decided.decided_by) == (
        "refusal",
        reason,
        "rules",
    )


@pytest.mark.parametrize(
    ("question", "break_type"),
    [
        ("Show payments with an award we never recorded", None),
        ("Outlays with no recorded obligation?", None),
        ("List awards where outlays exceeded the obligation", "outlay_exceeds_obligation"),
        ("Any de-obligations exceeding what was awarded?", "deobligation_exceeds_award"),
        ("Was any contract recorded twice?", "possible_duplicate_award"),
        ("Which reports came in as late arrivals?", "late_after_close"),
    ],
)
def test_known_anomalies_map_to_their_break_type(question, break_type):
    decided = by_rules(question)
    assert decided is not None
    assert decided.category == "anomaly_list"
    assert decided.spec is not None
    if break_type is None:
        assert decided.spec.absence_rule == "outlay_without_recorded_award"
    else:
        assert decided.spec.filters[0].value == break_type


def policy(question: str) -> str | None:
    decided = by_rules(question)
    return decided.category if decided else None


def test_policy_questions_need_the_far_in_capitals():
    assert policy("What does FAR part 32 say about advance payments?") == "policy"
    assert policy("Is a contractor required to report overpayments?") == "policy"
    assert by_rules("How much has Energy obligated so far?") is None


def test_the_project_word_is_not_a_forecast():
    assert by_rules("Total obligated on the Energy project award?") is None


def test_numeric_questions_go_to_the_model_and_its_spec_is_validated():
    spec = {
        "shape": "aggregate",
        "entity": "obligations",
        "metric": "sum_amount",
        "filters": [{"field": "awarding_agency", "op": "eq", "value": "Department of Energy"}],
    }
    decided, fake = ask(
        "Total Energy obligations?", json.dumps({"category": "numeric_aggregate", "spec": spec})
    )
    assert decided.category == "numeric_aggregate"
    assert decided.decided_by == "model"
    assert decided.spec is not None
    assert decided.spec.metric == "sum_amount"
    request = fake.requests[0]
    assert request.prompt_version == PROMPT_VERSION
    assert request.response_schema is not None
    assert "<question>Total Energy obligations?</question>" in request.messages[1].content
    assert "Department of Energy; Department of State" in request.messages[0].content
    assert "obligations: obligations and modifications" in request.messages[0].content


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        ("not json", "unreadable"),
        (json.dumps({"category": "gossip"}), "unknown_category"),
        (
            json.dumps({"category": "lookup", "spec": {"shape": "lookup", "entity": "ledger"}}),
            "invalid_spec",
        ),
        (json.dumps({"category": "lookup"}), "invalid_spec"),
        (json.dumps({"spec": None}), "unreadable"),
    ],
)
def test_unusable_model_answers_are_reported_not_guessed(reply, error):
    decided, _ = ask("Biggest Energy contract?", reply)
    assert (decided.category, decided.error) == (None, error)


def test_model_refusals_and_policy_are_accepted_with_known_reasons():
    decided, _ = ask(
        "Average age of contractors?",
        json.dumps({"category": "refusal", "refusal_reason": "no_data"}),
    )
    assert (decided.category, decided.refusal_reason) == ("refusal", "no_data")
    decided, _ = ask(
        "Average age of contractors?", json.dumps({"category": "refusal", "refusal_reason": "nope"})
    )
    assert decided.refusal_reason == "out_of_scope"
    decided, _ = ask("Can an agency pay in advance?", json.dumps({"category": "policy"}))
    assert decided.category == "policy"
