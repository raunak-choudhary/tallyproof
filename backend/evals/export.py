"""Export evaluation reports into the replay bundle for the dashboard.

Reports live in ``var/eval/<run>/report.json`` and are thrown away with the
run. Publishing one is a deliberate step: this copies chosen reports to
``frontend/public/replay/evals/<run>.json`` and rebuilds ``index.json`` from
whatever is in that folder, so the dashboard can list runs without a server.

Two refusals keep the published set honest. A harness check (fake mode, or a
cached run with missing recordings) is never exported, so a placeholder can't
be shown as a result. And a report whose questions, answers, or notes carry
contact details is refused, the same rule every committed dataset follows.

Usage::

    python -m evals.export var/eval/<run>/report.json [more reports...]
"""

import argparse
import json
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

from evals.readme_table import NotAQualityRunError
from evals.scoring import THRESHOLDS
from tallyproof_core.contact_data import find_contact_data
from tallyproof_pipeline.settings import REPO_ROOT

OUT = REPO_ROOT / "frontend" / "public" / "replay" / "evals"

# Top-level numbers the index carries, so the overview charts need only one file.
SUMMARY_KEYS = (
    "questions",
    "citation_precision",
    "citation_recall",
    "numeric_exactness",
    "answer_coverage",
    "refusal_f1",
    "anomaly_recall",
    "policy_section_accuracy",
    "quote_faithfulness",
    "injection_resistance",
    "fallback_rate",
    "free_number_rate",
    "integrity",
    "reconciliation_recall",
    "tokens",
    "latency_p50_ms",
    "latency_p95_ms",
)


class ContactDataError(ValueError):
    """The report carries contact details and must not be published."""


def run_name(report: dict[str, Any]) -> str:
    """The file stem for a report: its run time as a compact UTC stamp."""
    when = datetime.fromisoformat(report["run_at"])
    return when.strftime("%Y%m%dT%H%M%SZ")


def check(report: dict[str, Any]) -> None:
    """Refuse a harness check or a report with contact details."""
    if report.get("label") != "quality run":
        raise NotAQualityRunError("only quality runs are exported")
    for result in report.get("results", []):
        for field in ("question", "answer", "refusal", "notes"):
            value = result.get(field)
            text = " ".join(value) if isinstance(value, list) else str(value or "")
            if find_contact_data(text):
                raise ContactDataError(f"result {result.get('id')} carries contact details")


def summary(report: dict[str, Any], file: str) -> dict[str, Any]:
    """One index entry."""
    metrics = report["metrics"]
    return {
        "file": file,
        "run_at": report["run_at"],
        "commit": report.get("commit", "unknown"),
        "mode": report["mode"],
        "label": report["label"],
        "models": report["models"],
        "sets": {name: values.get("questions") for name, values in report["by_set"].items()},
        "metrics": {key: metrics.get(key) for key in SUMMARY_KEYS},
        "template_vs_held_out_numeric_gap": report.get("template_vs_held_out_numeric_gap"),
        "gate_failures": report.get("gate_failures", []),
    }


def rebuild_index(out: Path) -> dict[str, Any]:
    """Index every exported report in the folder, oldest first."""
    runs = []
    for path in sorted(out.glob("*.json")):
        if path.name == "index.json":
            continue
        report = json.loads(path.read_text())
        runs.append(summary(report, path.name))
    runs.sort(key=lambda r: r["run_at"])
    # The gates travel with the runs, so the dashboard draws the thresholds CI holds.
    with THRESHOLDS.open("rb") as handle:
        gates = tomllib.load(handle)
    index = {"runs": runs, "gates": gates}
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return index


def export(reports: list[Path], out: Path = OUT) -> list[Path]:
    """Copy each report into the bundle folder and rebuild the index."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for source in reports:
        report = json.loads(source.read_text())
        check(report)
        target = out / f"{run_name(report)}.json"
        target.write_text(json.dumps(report, indent=2, default=str) + "\n")
        written.append(target)
    rebuild_index(out)
    return written


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    """Export the given reports."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    try:
        written = export(args.reports, args.out)
    except (NotAQualityRunError, ContactDataError) as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1
    for path in written:
        print(f"exported {path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
