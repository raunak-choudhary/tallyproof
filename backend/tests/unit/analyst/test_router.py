"""Router rules and the model fallback. Phrasings here are not from the held-out set."""

import json

import pytest

from apps.analyst.llm import FakeClient
from apps.analyst.router import PROMPT_VERSION, Route, by_rules, route

AGENCIES = ["Department of Energy", "Department of State"]


def ask(question: str, reply: str = "{}") -> tuple[Route, FakeClient]:
    fake = FakeClient([reply, reply])  # an invalid spec gets one repair attempt
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


def test_the_structured_output_schema_describes_a_whole_spec():
    """Gemini fills exactly the schema it's given; an empty spec schema got empty specs."""
    from apps.analyst.query_spec import CATALOG
    from apps.analyst.router import ROUTER_SCHEMA

    spec = ROUTER_SCHEMA["properties"]["spec"]
    assert spec["required"] == ["shape", "entity"]
    assert set(spec["properties"]["entity"]["enum"]) == set(CATALOG)
    filter_fields = spec["properties"]["filters"]["items"]["properties"]["field"]["enum"]
    assert {"awarding_agency", "fiscal_year", "piid", "period_outlay"} <= set(filter_fields)
    assert "description" not in filter_fields


def test_an_invalid_spec_gets_one_repair_with_the_exact_error():
    broken = json.dumps({"category": "lookup", "spec": {"shape": "lookup", "entity": "awards"}})
    fixed = json.dumps(
        {
            "category": "lookup",
            "spec": {
                "shape": "lookup",
                "entity": "awards",
                "filters": [{"field": "piid", "op": "eq", "value": "P1"}],
                "fields": ["total_outlays"],
            },
        }
    )
    fake = FakeClient([broken, fixed])
    decided = route("Paid on P1?", fake, model="m", agencies=AGENCIES, max_tokens=300)
    assert decided.category == "lookup"
    assert decided.spec is not None
    assert len(fake.requests) == 2
    assert "a lookup needs filters" in fake.requests[1].messages[-1].content


def test_asking_what_the_regulation_says_is_policy_even_about_fraud():
    assert policy("What does the FAR say about fraud?") == "policy"
    assert policy("Under the regulation, when is a kickback illegal?") == "policy"
    assert policy("How does the FAR define a kickback?") == "policy"


@pytest.mark.parametrize(
    "question",
    [
        "Did the vendor on 47QSSC24F0S7X commit fraud under the regulations?",
        "Under the regulations, is this contractor guilty of fraud?",
        "Is Acme committing fraud under the FAR?",
        "What does the FAR say about whether this contractor committed fraud?",
    ],
)
def test_naming_the_regulation_doesnt_turn_a_verdict_into_a_policy_question(question):
    decided = by_rules(question)
    assert decided is not None
    assert decided.refusal_reason == "judgment_beyond_data"


def test_the_exception_is_only_for_judgment():
    # Only the judgment refusal yields to a policy question; the others still apply.
    poem = by_rules("Write me a poem about the FAR")
    assert poem is not None
    assert poem.refusal_reason == "out_of_scope"
    salary = by_rules("What salary does the FAR officer on this contract earn?")
    assert salary is not None
    assert salary.refusal_reason == "personal_data"
