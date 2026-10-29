"""Render an evaluation report as the README's results table.

Only quality runs belong in the README. A harness check (fake mode, or a cached
run with missing recordings) is refused, so a placeholder can never be mistaken
for a measured result.

Usage::

    python -m evals.readme_table var/eval/<run>/report.json

The commit comes from the report, which records what it measured.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

from tallyproof_pipeline.settings import REPO_ROOT

README = REPO_ROOT / "README.md"
START, END = "<!-- eval-table:start -->", "<!-- eval-table:end -->"
ROWS = (
    ("numeric_exactness", "Numeric exactness"),
    ("citation_precision", "Citation precision"),
    ("citation_recall", "Citation recall"),
    ("refusal_f1", "Refusal F1"),
    ("anomaly_recall", "Analyst anomaly recall"),
    ("answer_coverage", "Answer coverage"),
    ("quote_faithfulness", "Quote faithfulness"),
    ("injection_resistance", "Injection resistance"),
    ("reconciliation_recall", "Reconciliation recall"),
    ("integrity", "Integrity (proofs and quotes)"),
)


class NotAQualityRunError(ValueError):
    """The report is a harness check and must not be published."""


def table(report: dict[str, Any], commit: str | None = None) -> str:
    """The Markdown block that goes between the README markers."""
    commit = commit or str(report.get("commit", "unknown"))
    if report["label"] != "quality run":
        raise NotAQualityRunError("only quality runs go in the README")
    sets = report["by_set"]
    held = sets.get("held_out", {})
    template: dict[str, Any] = next((v for k, v in sets.items() if k != "held_out"), {})
    lines = [
        START,
        f"Run {report['run_at'][:10]} at commit `{commit[:7]}`, "
        f"router `{report['models']['router']}`, answer `{report['models']['answer']}`, "
        f"{report['metrics']['questions']} questions.",
        "",
        "| Metric | Template questions | Held-out questions |",
        "|---|---|---|",
    ]

    def cell(values: dict[str, Any], key: str) -> str:
        value = values.get(
            key, report["metrics"].get(key) if key == "reconciliation_recall" else None
        )
        return "" if value is None else f"{value:.2f}"

    lines += [f"| {label} | {cell(template, key)} | {cell(held, key)} |" for key, label in ROWS]
    return "\n".join([*lines, END])


def update(readme: str, block: str) -> str:
    """Replace the block between the markers."""
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(readme):
        raise ValueError("README has no eval-table markers")
    return pattern.sub(lambda _: block, readme)


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Write the table from one report into README.md."""
    report = json.loads(Path(sys.argv[1]).read_text())
    README.write_text(update(README.read_text(), table(report)))


if __name__ == "__main__":  # pragma: no cover
    main()
