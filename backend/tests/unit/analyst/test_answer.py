from datetime import date
from decimal import Decimal

import pytest

from apps.analyst.answer import Draft, Evidence, Quote, QuoteSource, from_query, render, verify
from apps.analyst.compiler import compile_spec
from apps.analyst.query_spec import QuerySpec


def evidence() -> Evidence:
    e = Evidence(filter_words="obligations where awarding agency is State and fiscal year is 2024")
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
        # Number words count as numbers.
        ("State obligated {{s1}} across fifteen awards [[c1]].", ("free_number:fifteen",)),
        (
            "Spending was two hundred thousand [[c1]].",
            ("free_number:two", "free_number:hundred", "free_number:thousand"),
        ),
        # A value can't be scaled, extended, signed, or joined to another.
        ("State obligated {{s1}} million [[c1]].", ("free_number:million", "slot_modified:s1")),
        ("State obligated {{s1}}k [[c1]].", ("slot_modified:s1",)),
        ("State obligated {{s1}}0 [[c1]].", ("free_number:0", "slot_modified:s1")),
        ("State obligated -{{s1}} [[c1]].", ("slot_modified:s1",)),
        ("State obligated {{s2}}{{s1}} [[c1]].", ("slot_joined:s2",)),
        ("State obligated {{s2}}.{{s1}} [[c1]].", ("slot_joined:s2",)),
        ("It had {{s2}} records, {{s1}} in all [[c1]].", ()),
        # Numerals beyond ASCII digits.
        ("State obligated ½ of it [[c1]].", ("free_number:½",)),
        ("State obligated \u0663 times [[c1]].", ("free_number:\u0663",)),
        # Digits from the question are allowed only when the filter shows them.
        ("State obligated {{s1}} in FY2024 [[c1]].", ()),
        ("The total was 987654321 [[c1]].", ("free_number:987654321",)),
    ],
)
def test_the_verifier_finds_free_numbers_and_unbound_labels(template, problems):
    assert verify(Draft(template), evidence()).problems == problems


def test_clauses_after_a_semicolon_or_a_lowercase_start_stand_alone():
    verdict = verify(
        Draft(
            "State obligated {{s1}} [[c1]]; the agency also broke the law. "
            "the CFO approved it. Spending at the U.S. level was {{s2}} records [[c1]]."
        ),
        evidence(),
    )
    assert verdict.ok
    assert verdict.sentences == (
        "State obligated {{s1}} [[c1]];",
        "Spending at the U.S. level was {{s2}} records [[c1]].",
    )


def test_sentences_without_a_slot_or_citation_are_dropped():
    verdict = verify(
        Draft("State obligated {{s1}} [[c1]]. The CFO approved every award. Ask again later."),
        evidence(),
    )
    assert verdict.ok
    assert verdict.sentences == ("State obligated {{s1}} [[c1]].",)
    assert render(verdict.sentences, evidence()) == "State obligated $375,597.44 [[c1]]."


def test_quotes_must_be_exact_substrings_of_the_leaf_ignoring_line_breaks():
    good = Quote(
        "q1", "A bilateral modification is a contract modification signed by both parties."
    )
    assert verify(Draft("FAR 43.103 says [[q1]].", (good,)), evidence()).ok
    bent = Quote("q1", "A bilateral modification is signed by both parties.")
    assert verify(Draft("It says [[q1]].", (bent,)), evidence()).problems == ("quote_mismatch:q1",)
    assert verify(Draft("It says [[q1]].", (Quote("q4", "x"),)), evidence()).problems == (
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


def test_a_number_from_the_regulation_needs_the_quote_that_holds_it():
    e = evidence()
    e.sources["q1"] = QuoteSource(
        "q1",
        "evt_far",
        9,
        "43.201",
        "General.",
        "issued on Standard Form 30",
        "issued on Standard Form 30",
    )
    e.sources["q2"] = QuoteSource("q2", "evt_far2", 10, "4.101", "Signatures.", "x", "y")
    paraphrase = Draft("Change orders use Standard Form 30 [[q1]].")
    assert verify(paraphrase, e).problems == ("free_number:30",)
    quoted = Draft(
        "Change orders use Standard Form 30 [[q1]].", (Quote("q1", "issued on Standard Form 30"),)
    )
    assert verify(quoted, e).ok
    wrong_source = Draft(
        "Change orders use Standard Form 30 [[q2]].", (Quote("q1", "issued on Standard Form 30"),)
    )
    assert "free_number:30" in verify(wrong_source, e).problems


def test_every_value_shown_carries_its_citation():
    e = Evidence()
    a = e.add_citation([("evt_a", 1)], "row 1")
    b = e.add_citation([("evt_b", 2)], "row 2")
    e.add_slot("text", "AWD-1", "award key", a)
    e.add_slot("text", "AWD-2", "award key", b)
    assert (
        render(["Duplicates: {{s1}} and {{s2}} [[c2]]."], e)
        == "Duplicates: AWD-1 [[c1]] and AWD-2 [[c2]]."
    )


def test_a_sentence_mixing_groups_marks_each_value_with_its_own_citation():
    e = Evidence()
    hhs = e.add_citation([("evt_a", 1)], "records where agency is HHS")
    dot = e.add_citation([("evt_b", 2)], "records where agency is DOT")
    e.add_slot("text", "HHS", "agency", hhs)
    e.add_slot("money", Decimal(10), "total", hhs)
    e.add_slot("text", "DOT", "agency", dot)
    e.add_slot("money", Decimal(1), "total", dot)
    swapped = "{{s1}} spent {{s4}} and {{s3}} spent {{s2}} [[c1]] [[c2]]."
    assert render([swapped], e) == (
        "HHS [[c1]] spent $1.00 [[c2]] and DOT [[c2]] spent $10.00 [[c1]] [[c2]]."
    )
    one_group = "{{s1}} spent {{s2}} [[c1]]."
    assert render([one_group], e) == "HHS spent $10.00 [[c1]]."


def test_a_full_list_says_more_may_match():
    s = spec(shape="list", entity="obligations", limit=2, fields=["amount"])
    compiled = compile_spec(s, tree_size=10, max_rows=100)
    full = from_query(
        s, compiled, [], [("evt_a", 1, Decimal(1)), ("evt_b", 2, Decimal(2))], tree_size=10
    )
    assert full.filter_words.endswith("more records may match")
    short = from_query(s, compiled, [], [("evt_a", 1, Decimal(1))], tree_size=10)
    assert "more records may match" not in short.filter_words


def test_an_answer_made_only_of_quotes_shows_them():
    assert (
        render([], evidence(), [Quote("q1", "signed by both parties")])
        == '"signed by both parties" [[q1]]'
    )


def test_a_citation_says_when_it_is_a_sample():
    e = Evidence()
    full = e.add_citation([("evt_a", 1), ("evt_b", 2)], "all", total=2)
    part = e.add_citation([("evt_a", 1)], "some", total=40)
    assert e.citations[full].sample_of is None
    assert e.citations[part].sample_of == 40
    assert e.sampled


def policy_evidence() -> Evidence:
    e = Evidence(assurance="policy")
    e.sources["q1"] = QuoteSource(
        "q1", "evt_far", 9, "43.103", "Types of contract modifications.", "excerpt",
        "(a) Bilateral. A bilateral modification is a contract modification "
        "signed by both parties.",
    )  # fmt: skip
    return e


def test_a_policy_answer_needs_a_quote():
    bare = Draft("Bilateral modifications need both parties [[q1]].")
    assert verify(bare, policy_evidence()).problems == ("quote_required",)
    quoted = Draft(
        "Bilateral modifications need both parties [[q1]].",
        (Quote("q1", "signed by both parties"),),
    )
    assert verify(quoted, policy_evidence()).ok


def test_text_quoted_inline_must_come_from_a_source_the_sentence_cites():
    quote = (Quote("q1", "signed by both parties"),)
    honest = Draft('The FAR says a bilateral change is "signed by both parties" [[q1]].', quote)
    assert verify(honest, policy_evidence()).ok
    curly = Draft("The FAR says it is “signed by both parties” [[q1]].", quote)
    assert verify(curly, policy_evidence()).ok
    invented = Draft('The FAR says it "may be signed by either party alone" [[q1]].', quote)
    assert verify(invented, policy_evidence()).problems == ("inline_quote_unchecked",)
    uncited = Draft('Total {{s1}} was "signed by both parties" [[c1]].')
    assert verify(uncited, evidence()).problems == ("inline_quote_unchecked",)
