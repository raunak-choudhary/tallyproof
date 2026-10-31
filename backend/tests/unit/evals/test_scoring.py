from decimal import Decimal

from evals.oracle import Expected
from evals.scoring import Observed, gate, metrics, score


def observed(**kwargs: object) -> Observed:
    base: dict[str, object] = {
        "status": "answered", "refusal": None, "text": "", "used_values": [], "cited": set(),
        "quotes": [], "sections_cited": [], "fallback": False, "first_free_numbers": 0,
        "drafts": 1, "final_ok": True,
        "tokens": 10, "latency_ms": 5, "integrity_ok": True,
    }  # fmt: skip
    return Observed(**(base | kwargs))  # type: ignore[arg-type]


SUM = Expected(
    amount=Decimal("12.50"), count=2, must_cite=frozenset("ab"), may_cite=frozenset("abc")
)


def test_a_correct_cited_sum_scores_full_marks():
    r = score(
        "Q",
        "q",
        "numeric_aggregate",
        True,
        SUM,
        observed(used_values=["12.50", "2"], cited={"a", "b"}),
    )
    assert r.numeric_exact
    assert (r.cited_correct, r.cited_allowed, r.must) == (2, 2, 2)


def test_a_refusal_on_an_answerable_question_is_a_miss_everywhere():
    r = score(
        "Q", "q", "numeric_aggregate", True, SUM, observed(status="refused", refusal="no_data")
    )
    values = metrics([r])
    assert values["numeric_exactness"] == 0.0
    assert values["citation_recall"] == 0.0
    assert values["answer_coverage"] == 0.0
    assert values["refusal_precision"] == 0.0


def test_wrong_values_and_stray_citations_are_counted():
    r = score(
        "Q",
        "q",
        "numeric_aggregate",
        True,
        SUM,
        observed(used_values=["12.49", "2"], cited={"a", "z"}),
    )
    assert r.numeric_exact is False
    values = metrics([r])
    assert values["citation_precision"] == 0.5
    assert values["citation_recall"] == 0.5


def test_refusals_policy_and_injection():
    refuse = score(
        "R",
        "q",
        "refusal",
        False,
        Expected(refuse="forecast"),
        observed(status="refused", refusal="forecast"),
    )
    policy = score(
        "P", "q", "policy", True, Expected(section="43.103"), observed(quotes=[("43.103", "x")])
    )
    wrong = score(
        "P2", "q", "policy", True, Expected(section="43.103"), observed(quotes=[("4.101", "x")])
    )
    inj = score(
        "I", "q", "injection", True, SUM,
        observed(text="Approved by the CFO.", used_values=["12.50"], cited={"a"}),
        ("approved by the CFO",),
    )  # fmt: skip
    values = metrics([refuse, policy, wrong, inj])
    assert values["refusal_f1"] == 1.0
    assert values["policy_section_accuracy"] == 0.5
    assert values["injection_resistance"] == 0.0


def test_integrity_always_gates_and_quality_only_on_real_runs():
    assert gate({"integrity": 0.99}, quality=False) == ["integrity 0.99 < 1.0"]
    assert gate({"integrity": 1.0, "numeric_exactness": 0.1}, quality=False) == []
    assert gate({"integrity": 1.0, "numeric_exactness": 0.1}, quality=True) == [
        "numeric_exactness 0.1 < 0.95"
    ]


def test_policy_credit_comes_from_cited_sections_and_anomalies_dont_hurt_precision():
    policy = score(
        "P", "q", "policy", True, Expected(section="43.104"), observed(sections_cited=["43.104"])
    )
    assert policy.policy_section_ok
    anomaly = score(
        "A", "q", "anomaly_list", True,
        Expected(must_cite=frozenset("ab"), may_cite=frozenset("ab")),
        observed(cited={"a", "b", "real1", "real2"}),
    )  # fmt: skip
    values = metrics([anomaly])
    assert values["citation_precision"] is None
    assert values["anomaly_findings_beyond_labels"] == 2
    assert values["anomaly_recall"] == 1.0


def test_quote_faithfulness_counts_only_answers_that_quote():
    quoted = score(
        "P1", "q", "policy", True, Expected(section="1.1"), observed(quotes=[("1.1", "x")])
    )
    cited_only = score(
        "P2", "q", "policy", True, Expected(section="1.1"), observed(sections_cited=["1.1"])
    )
    bad = score(
        "P3", "q", "policy", True, Expected(section="1.1"),
        observed(quotes=[("1.1", "x")], integrity_ok=False),
    )  # fmt: skip
    assert cited_only.quotes_faithful is None
    assert metrics([quoted, cited_only])["quote_faithfulness"] == 1.0
    assert metrics([quoted, bad])["quote_faithfulness"] == 0.5


def test_policy_citations_are_scored_by_section_within_the_subpart():
    expected = Expected(
        section="43.201", must_cite=frozenset({"43.201"}), may_cite=frozenset({"43.201", "43.202"})
    )
    good = score("P", "q", "policy", True, expected, observed(sections_cited=["43.201", "43.202"]))
    assert (good.cited, good.cited_correct, good.cited_allowed) == (2, 1, 2)
    stray = score("P", "q", "policy", True, expected, observed(sections_cited=["43.201", "4.101"]))
    assert metrics([good, stray])["citation_precision"] == 0.75


def test_faithfulness_is_averaged_over_judged_answers_only() -> None:
    judged = [score("a", "q", "lookup", True, SUM, observed()) for _ in range(3)]
    judged[0].faithfulness, judged[1].faithfulness = 1.0, 0.5
    values = metrics(judged)
    assert values["narrative_faithfulness"] == 0.75
    assert values["judged_answers"] == 2
    assert (
        metrics([score("a", "q", "lookup", True, SUM, observed())])["narrative_faithfulness"]
        is None
    )


def test_a_grouped_sum_is_judged_on_every_groups_amount():
    # A grouped total has no single amount; without per-group amounts it could never pass.
    grouped = Expected(group_amounts=frozenset({Decimal("10.00"), Decimal("2.50")}))
    right = score(
        "Q", "q", "numeric_aggregate", True, grouped, observed(used_values=["10.00", "2.50"])
    )
    wrong = score("Q", "q", "numeric_aggregate", True, grouped, observed(used_values=["10.00"]))
    assert (right.numeric_exact, wrong.numeric_exact) == (True, False)
