from decimal import Decimal

from evals.oracle import Expected
from evals.scoring import Observed, gate, metrics, score


def observed(**kwargs: object) -> Observed:
    base: dict[str, object] = {
        "status": "answered", "refusal": None, "text": "", "used_values": [], "cited": set(),
        "quotes": [], "fallback": False, "first_free_numbers": 0, "drafts": 1, "final_ok": True,
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
