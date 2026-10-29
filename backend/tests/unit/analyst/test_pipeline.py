"""The question-to-answer flow with a fake model and a fake database."""

import json
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

from apps.analyst.llm import Budget, BudgetedClient, FakeClient, LLMRequest
from apps.analyst.pipeline import Models, ask
from apps.analyst.query_spec import MAX_LIST_ROWS
from apps.analyst.retrieval import Chunk, Hit, PolicyLeaf

MODELS = Models(router="router-m", answer="answer-m", max_output_tokens=400, max_rows=100)
SUM_SPEC = {
    "shape": "aggregate",
    "entity": "obligations",
    "metric": "sum_amount",
    "filters": [{"field": "awarding_agency", "op": "eq", "value": "Department of State"}],
}
FAR = PolicyLeaf(
    "evt_far", 7, "43.202", "Authority to issue change orders.",
    "Generally, only contracting officers acting within the scope of their authority are "
    "empowered to execute change orders.",
)  # fmt: skip


class Database:
    def __init__(self, **answers: list[tuple[Any, ...]]) -> None:
        self.columns = ["event_id", "leaf_index", "mean"]
        self.answers = answers
        self.sql: list[str] = []

    def run(self, sql: str, params: Sequence[Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
        self.sql.append(sql)
        if "break_events" in sql:
            return ["event_id", "leaf_index"], self.answers.get("break_events", [])
        if sql.startswith("SELECT coalesce"):
            return ["value", "row_count"], self.answers.get("value", [])
        if "fallback" in self.answers and "LIMIT" in sql and "ORDER BY t." not in sql:
            return self.columns, self.answers["fallback"]
        return ["event_id", "leaf_index"], self.answers.get("evidence", [])


def model(**replies: Any) -> Callable[[LLMRequest], str]:
    """Answer by prompt version; a list is consumed in order."""

    def reply(request: LLMRequest) -> str:
        value = replies[request.prompt_version]
        return str(value.pop(0) if isinstance(value, list) else value)

    return reply


def search(hits: list[Hit]) -> Callable[[str, int], Sequence[Hit]]:
    return lambda question, k: hits[:k]


def run(question: str, client: Any, db: Database, hits: list[Hit] | None = None) -> Any:
    return ask(
        question, client=client, executor=db, search=search(hits or []), models=MODELS,
        agencies=["Department of State"], tree_size=50,
    )  # fmt: skip


STATE_DB: dict[str, list[tuple[Any, ...]]] = dict(
    value=[(Decimal("375597.44"), 2)],
    evidence=[("evt_a", 1, Decimal("300000.00")), ("evt_b", 2, Decimal("75597.44"))],
)


def test_a_numeric_question_is_answered_with_bound_values_and_citations():
    fake = FakeClient(
        model(**{
            "router.v2": json.dumps({"category": "numeric_aggregate", "spec": SUM_SPEC}),
            "composer.v4": json.dumps(
                {"answer": "State obligated {{s1}} over {{s2}} actions [[c1]]."}
            ),
        })
    )  # fmt: skip
    db = Database(**STATE_DB)
    answer = run("How much did State obligate?", fake, db)
    assert answer.status == "answered"
    assert answer.text == "State obligated $375,597.44 over 2 actions [[c1]]."
    assert answer.evidence.citations["c1"].event_ids == ("evt_a", "evt_b")
    assert "awarding agency is Department of State" in answer.evidence.filter_words
    assert all("< %s" in sql for sql in db.sql)  # pinned to the checkpoint
    composer_prompt = fake.requests[-1].messages[1].content
    assert "{{s1}} money:" in composer_prompt
    assert "$375,597.44" in composer_prompt


def test_a_free_number_gets_one_repair_and_then_a_refusal():
    replies: list[str] = [
        json.dumps({"answer": "State obligated $375,597.44 [[c1]]."}),
        json.dumps({"answer": "State obligated {{s1}} [[c1]]."}),
    ]
    fake = FakeClient(
        model(
            **{
                "router.v2": json.dumps({"category": "numeric_aggregate", "spec": SUM_SPEC}),
                "composer.v4": replies,
            }
        )
    )
    answer = run("How much did State obligate?", fake, Database(**STATE_DB))
    assert answer.status == "answered"
    assert [v.free_numbers for v in answer.trace.verdicts] == [1, 0]
    assert "free_number:$375,597.44" in fake.requests[-1].messages[-1].content

    stubborn = json.dumps({"answer": "State obligated 375597.44 dollars [[c1]]."})
    fake = FakeClient(
        model(
            **{
                "router.v2": json.dumps({"category": "numeric_aggregate", "spec": SUM_SPEC}),
                "composer.v4": stubborn,
            }
        )
    )
    answer = run("How much did State obligate?", fake, Database(**STATE_DB))
    assert (answer.status, answer.refusal) == ("refused", "unverifiable_claim")
    assert answer.text == ""


def test_rule_refusals_never_call_the_model():
    fake = FakeClient([])
    answer = run("What is the CEO's home address?", fake, Database())
    assert (answer.status, answer.refusal) == ("refused", "personal_data")
    assert fake.requests == []


def test_policy_answers_quote_exactly_and_cite_the_leaf():
    hit = Hit(Chunk(FAR, 0, len(FAR.text)), 1.0)
    quote = (
        "only contracting officers acting within the scope of their authority "
        "are empowered to execute change orders"
    )
    fake = FakeClient(
        model(
            **{
                "composer.v4": json.dumps(
                    {
                        "answer": "FAR 43.202 limits this [[q1]].",
                        "quotes": [{"source": "q1", "text": quote}],
                    }
                )
            }
        )
    )
    answer = run("Who may sign a change order under the FAR?", fake, Database(), [hit])
    assert answer.status == "answered"
    assert answer.evidence.sources["q1"].event_id == "evt_far"
    assert answer.quotes[0].text == quote


def test_anomaly_lists_cite_the_events_behind_each_break():
    composer = json.dumps({"answer": "One award was paid more than obligated: {{s2}} [[c1]]."})
    fake = FakeClient(model(**{"composer.v4": composer}))
    db = Database(
        evidence=[("brk_1", 40, "outlay_exceeds_obligation", "AWD1", Decimal("10.00"))],
        break_events=[("evt_award", 3), ("evt_outlay", 39)],
    )
    answer = run("Which awards were paid more than obligated?", fake, db)
    assert answer.status == "answered"
    assert answer.evidence.citations["c1"].event_ids == ("evt_award", "evt_outlay")


def test_an_ambiguous_lookup_and_empty_results_are_refused():
    spec = {
        "shape": "lookup",
        "entity": "obligations",
        "filters": [{"field": "piid", "op": "eq", "value": "P1"}],
        "fields": ["amount"],
    }
    route = json.dumps({"category": "lookup", "spec": spec})
    two = Database(evidence=[("evt_a", 1, Decimal(1)), ("evt_b", 2, Decimal(2))])
    assert (
        run("Amount on P1?", FakeClient(model(**{"router.v2": route})), two).refusal == "ambiguous"
    )
    assert (
        run("Amount on P1?", FakeClient(model(**{"router.v2": route})), Database()).refusal
        == "no_evidence"
    )


def test_without_the_fallback_an_inexpressible_question_is_refused():
    fake = FakeClient(model(**{"router.v2": "not json"}))
    answer = run("Average award size?", fake, Database())
    assert (answer.status, answer.refusal) == ("refused", "not_expressible")
    assert "fallback-sql.v1" not in {r.prompt_version for r in fake.requests}


FALLBACK = Models(
    router="router-m", answer="answer-m", max_output_tokens=400, max_rows=100, allow_fallback=True
)


def ask_with_fallback(question: str, client: Any, db: Database) -> Any:
    return ask(
        question, client=client, executor=db, search=search([]), models=FALLBACK,
        agencies=["Department of State"], tree_size=50,
    )  # fmt: skip


def test_the_fallback_path_runs_only_guarded_pinned_sql_and_is_labeled():
    fallback_sql = json.dumps(
        {"sql": "SELECT event_id, leaf_index, amount AS mean FROM obligations"}
    )
    fake = FakeClient(model(**{
        "router.v2": json.dumps({
            "category": "numeric_aggregate",
            "spec": {"shape": "aggregate", "entity": "obligations", "metric": "avg"},
        }),
        "fallback-sql.v1": fallback_sql,
        "composer.v4": json.dumps({"answer": "The first award averaged {{s1}} [[c1]]."}),
    }))  # fmt: skip
    db = Database(fallback=[("evt_a", 1, Decimal("5.50"))])
    answer = ask_with_fallback("Average award size?", fake, db)
    assert answer.status == "answered"
    assert answer.evidence.assurance == "lower_assurance"
    assert answer.trace.used_fallback
    assert db.sql == [
        "SELECT event_id, leaf_index, amount AS mean FROM obligations "
        "WHERE obligations.leaf_index < 50 LIMIT 100"
    ]


FORGED = "SELECT event_id, leaf_index, CAST('987654321.00' AS DECIMAL) AS amount FROM obligations"
DIVIDES_BY_ZERO = "SELECT event_id, leaf_index FROM obligations WHERE 1 / 0 = 1"


def test_the_fallback_refuses_forged_values_and_failing_queries():
    forged = FakeClient(model(**{
        "router.v2": "not json",
        "fallback-sql.v1": json.dumps({"sql": FORGED}),
    }))  # fmt: skip
    assert ask_with_fallback("Total?", forged, Database()).refusal == "unsafe_query"
    hostile = FakeClient(
        model(
            **{
                "router.v2": "not json",
                "fallback-sql.v1": json.dumps({"sql": "DELETE FROM obligations"}),
            }
        )
    )
    assert ask_with_fallback("Average award size?", hostile, Database()).refusal == "unsafe_query"

    class Failing(Database):
        def run(self, sql: str, params: Sequence[Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
            from django.db import DataError

            raise DataError("division by zero")

    failing = FakeClient(model(**{
        "router.v2": "not json",
        "fallback-sql.v1": json.dumps({"sql": DIVIDES_BY_ZERO}),
    }))  # fmt: skip
    assert ask_with_fallback("Total?", failing, Failing()).refusal == "unsafe_query"

    uncited = FakeClient(model(**{
        "router.v2": "not json",
        "fallback-sql.v1": json.dumps({"sql": "SELECT sum(amount) AS total FROM obligations"}),
    }))  # fmt: skip
    db = Database(fallback=[(Decimal(5),)])
    db.columns = ["total"]
    assert ask_with_fallback("Total?", uncited, db).refusal == "no_evidence"


def test_budget_exhaustion_is_a_typed_refusal():
    client = BudgetedClient(FakeClient(lambda r: "{}"), Budget(max_requests=0, max_tokens=1))
    answer = run("How much did State obligate?", client, Database(**STATE_DB))
    assert (answer.status, answer.refusal) == ("refused", "budget_exceeded")


def test_repair_messages_explain_what_to_do():
    from apps.analyst.answer import Evidence, QuoteSource, Verdict
    from apps.analyst.pipeline import repair_message

    policy = Evidence()
    policy.sources["q1"] = QuoteSource(
        "q1", "evt", 1, "32.501-1", "Rates.", "80 percent", "80 percent"
    )
    message = repair_message(Verdict(("unbound_slot:s1",), ()), policy)
    assert "write each number exactly as the source shows it" in message
    numeric = Evidence()
    numeric.add_slot("money", Decimal(1), "total", None)
    message = repair_message(Verdict(("free_number:$1.00", "unknown_citation:c9"), ()), numeric)
    assert "Replace every number you typed" in message
    assert "Cite only the" in message
    codes = ("slot_modified:s1", "quote_required", "inline_quote_unchecked")
    message = repair_message(Verdict(codes, ()), numeric)
    assert "Write each slot on its own" in message
    assert "at least one passage" in message
    assert "only if it is copied exactly" in message


def test_a_total_over_the_citation_cap_is_answered_with_a_labelled_sample():
    small = Models(router="router-m", answer="answer-m", max_output_tokens=400, max_rows=2)
    composed = json.dumps({"answer": "State obligated {{s1}} over {{s2}} actions [[c1]]."})
    routed = json.dumps({"category": "numeric_aggregate", "spec": SUM_SPEC})
    fake = FakeClient(model(**{"router.v2": routed, "composer.v4": composed}))
    db = Database(
        value=[(Decimal("500.00"), 5)],
        evidence=[
            ("evt_a", 1, Decimal(100)),
            ("evt_b", 2, Decimal(100)),
            ("evt_c", 3, Decimal(100)),
        ],
    )
    answer = ask(
        "How much did State obligate?", client=fake, executor=db, search=search([]), models=small,
        agencies=["Department of State"], tree_size=50,
    )  # fmt: skip
    assert answer.status == "answered"
    assert answer.text == "State obligated $500.00 over 5 actions [[c1]]."
    assert answer.evidence is not None
    citation = answer.evidence.citations["c1"]
    assert citation.event_ids == ("evt_a", "evt_b")
    assert citation.sample_of == 5
    assert citation.words == "the first 2 of the 5 records counted, in log order"
    assert answer.evidence.sampled


def test_lookups_and_absence_lists_over_the_cap_still_refuse():
    small = Models(router="router-m", answer="answer-m", max_output_tokens=400, max_rows=1)
    absence = {
        "shape": "absence",
        "entity": "outlays",
        "absence_rule": "outlay_without_recorded_award",
    }
    route = json.dumps({"category": "anomaly_list", "spec": absence})
    db = Database(evidence=[("evt_a", 1, "A", Decimal(1)), ("evt_b", 2, "B", Decimal(2))])
    answer = ask(
        "Outlays for awards with no obligation on file?",
        client=FakeClient(model(**{"router.v2": route})), executor=db, search=search([]),
        models=small, agencies=[], tree_size=50,
    )  # fmt: skip
    assert answer.refusal == "too_broad"


def test_too_many_groups_is_too_broad():
    by_agency = {**SUM_SPEC, "filters": [], "group_by": "awarding_agency"}
    fake = FakeClient(model(**{
        "router.v2": json.dumps({"category": "numeric_aggregate", "spec": by_agency}),
    }))  # fmt: skip

    class ManyGroups(Database):
        def run(self, sql: str, params: Sequence[Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
            if "GROUP BY" in sql:
                groups = [(f"Agency {n}", Decimal(n), 1) for n in range(MAX_LIST_ROWS + 1)]
                return ["grp", "value", "row_count"], groups
            return super().run(sql, params)

    answer = run("Total awarded by every agency?", fake, ManyGroups())
    assert (answer.status, answer.refusal) == ("refused", "too_broad")
