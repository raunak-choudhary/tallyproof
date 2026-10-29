import pytest

from evals.readme_table import END, START, NotAQualityRunError, table, update

REPORT = {
    "label": "quality run",
    "run_at": "2026-10-29T03:00:00+00:00",
    "models": {"router": "r-model", "answer": "a-model"},
    "commit": "abc1234def",
    "metrics": {"questions": 218, "reconciliation_recall": 1.0},
    "by_set": {
        "full": {"numeric_exactness": 0.96, "integrity": 1.0},
        "held_out": {"numeric_exactness": 0.9, "integrity": 1.0},
    },
}


def test_a_quality_run_renders_template_and_held_out_columns():
    block = table(REPORT)
    assert block.startswith(START)
    assert block.endswith(END)
    assert "commit `abc1234`" in block
    assert "| Numeric exactness | 0.96 | 0.90 |" in block
    assert "| Reconciliation recall | 1.00 | 1.00 |" in block


def test_harness_checks_never_reach_the_readme():
    with pytest.raises(NotAQualityRunError):
        table({**REPORT, "label": "harness check"}, "abc")


def test_only_the_marked_block_changes():
    readme = f"intro\n{START}\nold\n{END}\noutro\n"
    assert update(readme, f"{START}\nnew\n{END}") == f"intro\n{START}\nnew\n{END}\noutro\n"
    with pytest.raises(ValueError, match="markers"):
        update("no markers", "x")
