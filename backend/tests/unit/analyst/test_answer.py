from datetime import date
from decimal import Decimal

import pytest

from apps.analyst.answer import Draft, Evidence, Quote, QuoteSource, from_query, render, verify
from apps.analyst.compiler import compile_spec
from apps.analyst.query_spec import QuerySpec

QUESTION = "What did State obligate in FY2024?"


def evidence() -> Evidence:
    e = Evidence(filter_words="obligations where awarding agency is State")
    cite = e.add_citation([("evt_a", 1), ("evt_b", 2)], "the 2 records counted")
    e.add_slot("money", Decimal("375597.44"), "total", cite)
    e.add_slot("count", 2, "number of records", cite)
    e.sources["q1"] = QuoteSource(
        "q1", "evt_far", 9, "43.103", "Types of contract modifications.", "excerpt",
        "(a) Bilateral. A bilateral modification is a contract modification\n"
        "signed by both parties.",
    )  # fmt: skip
    return e


@pytest.mark.parametrize(
    ("template", "problems"),
    [
        ("State obligated {{s1}} across {{s2}} records in FY2024 [[c1]].", ()),
        ("State obligated $375,597.44 in FY2024 [[c1]].", ("free_number:$375,597.44",)),
        ("State obligated {{s1}} over 2 actions [[c1]].", ("free_number:2",)),
        ("State obligated {{s9}} [[c1]].", ("unbound_slot:s9",)),
        ("State obligated {{s1}} [[c7]].", ("unknown_citation:c7",)),
        ("Nothing to cite here.", ("no_claims",)),
        ("It was ~375k [[c1]].", ("free_number:375k",)),
    ],
)
def test_the_verifier_finds_free_numbers_and_unbound_labels(template, problems):
    assert verify(Draft(template), evidence(), QUESTION).problems == problems


def test_sentences_without_a_slot_or_citation_are_dropped():
    verdict = verify(
        Draft("State obligated {{s1}} [[c1]]. The CFO approved every award. Ask again later."),
        evidence(),
        QUESTION,
    )
    assert verdict.ok
    assert verdict.sentences == ("State obligated {{s1}} [[c1]].",)
    assert render(verdict.sentences, evidence()) == "State obligated $375,597.44 [[c1]]."


def test_quotes_must_be_exact_substrings_of_the_leaf_ignoring_line_breaks():
    good = Quote(
        "q1", "A bilateral modification is a contract modification signed by both parties."
    )
    assert verify(Draft("FAR 43.103 says [[q1]].", (good,)), evidence(), QUESTION).ok
    bent = Quote("q1", "A bilateral modification is signed by both parties.")
    assert verify(Draft("It says [[q1]].", (bent,)), evidence(), QUESTION).problems == (
        "quote_mismatch:q1",
    )
    assert verify(Draft("It says [[q1]].", (Quote("q4", "x"),)), evidence(), QUESTION).problems == (
        "unknown_citation:q4",
    )


def test_money_and_counts_render_for_readers():
    e = Evidence()
    e.add_slot("money", Decimal("-709.56"), "amount", None)
    e.add_slot("count", 12345, "records", None)
    e.add_slot("date", date(2023, 10, 10), "action date", None)
    assert render(["{{s1}} {{s2}} {{s3}}"], e) == "-$709.56 12,345 2023-10-10"


def spec(**kwargs: object) -> QuerySpec:
    return QuerySpec.model_validate(kwargs)


def test_an_aggregate_binds_its_value_and_cites_every_contributing_row():
    s = spec(shape="aggregate", entity="obligations", metric="sum_amount")
    compiled = compile_spec(s, tree_size=10, max_rows=100)
    rows = [("evt_a", 1, Decimal(5)), ("evt_b", 2, Decimal(7))]
    e = from_query(s, compiled, [(Decimal(12), 2)], rows, tree_size=10)
    assert [(x.kind, x.value) for x in e.slots.values()] == [("money", Decimal(12)), ("count", 2)]
    assert e.citations["c1"].event_ids == ("evt_a", "evt_b")
    assert e.filter_words == "total of obligations and modifications"


def test_a_max_with_fields_binds_the_extreme_rows_fields():
    s = spec(shape="aggregate", entity="obligations", metric="max_amount", fields=["piid"])
    compiled = compile_spec(s, tree_size=10, max_rows=100)
    e = from_query(s, compiled, [(Decimal(9), 3)], [("evt_x", 4, Decimal(9), "P-1")], tree_size=10)
    assert [x.value for x in e.slots.values()] == [Decimal(9), 3, "P-1"]
    assert e.citations["c1"].event_ids == ("evt_x",)


def test_groups_cite_only_their_own_rows():
    s = spec(
        shape="aggregate", entity="obligations", metric="sum_amount", group_by="awarding_agency",
        limit=1,
    )  # fmt: skip
    compiled = compile_spec(s, tree_size=10, max_rows=100)
    rows = [
        ("evt_a", 1, "HHS", Decimal(5)),
        ("evt_b", 2, "DOT", Decimal(1)),
        ("evt_c", 3, "HHS", Decimal(5)),
    ]
    e = from_query(s, compiled, [("HHS", Decimal(10), 2)], rows, tree_size=10)
    assert e.citations["c1"].event_ids == ("evt_a", "evt_c")
    assert [x.value for x in e.slots.values()] == ["HHS", Decimal(10), 2]


def test_list_lookup_and_absence_rows_each_get_a_citation():
    s = spec(shape="list", entity="obligations", fields=["piid", "amount", "action_date"], limit=5)
    compiled = compile_spec(s, tree_size=10, max_rows=100)
    rows = [("evt_a", 1, "P1", Decimal(1), date(2024, 1, 2)), ("evt_b", 2, "P2", None, None)]
    e = from_query(s, compiled, [], rows, tree_size=10)
    assert list(e.citations) == ["c1", "c2"]
    assert [(x.kind, x.citation) for x in e.slots.values()] == [
        ("text", "c1"), ("money", "c1"), ("date", "c1"), ("text", "c2"),
    ]  # fmt: skip
    a = spec(shape="absence", entity="outlays", absence_rule="outlay_without_recorded_award")
    e = from_query(
        a,
        compile_spec(a, tree_size=10, max_rows=5),
        [],
        [("evt_o", 3, "AWD", Decimal(4))],
        tree_size=10,
    )
    assert [x.value for x in e.slots.values()] == ["AWD", Decimal(4)]


def test_numbers_from_a_cited_regulation_are_allowed():
    e = evidence()
    e.sources["q1"] = QuoteSource(
        "q1", "evt_far", 9, "43.201", "General.", "issued on Standard Form 30", "x"
    )
    assert verify(Draft("Change orders use Standard Form 30 [[q1]]."), e, QUESTION).ok
    assert not verify(Draft("Change orders use Standard Form 31 [[q1]]."), e, QUESTION).ok
