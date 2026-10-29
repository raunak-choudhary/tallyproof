"""Fail a pull request whose analyst changes went unmeasured by the smoke evaluation.

Pull requests replay recorded model responses. When a change alters a prompt, the
question sets, or the data the questions are asked about, the recordings no longer
match, the run falls back to a scripted client, and it's labeled a harness check:
integrity still gates, quality doesn't. On its own that would let such a change pass
with no evidence about answer quality. This check fails it instead, and says how to
record fresh responses.

A harness check on a pull request that touches none of those paths still passes.

Usage:
    python scripts/ci/check_eval_recordings.py <git revision range>
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "var" / "eval"

MEASURED = (
    "backend/apps/analyst/",
    "backend/evals/questions/",
    "backend/corpus/",
    "testdata/eval/",
)
"""Paths whose changes alter what the smoke evaluation asks or how it's answered."""


def newest_report(folder: Path = REPORTS) -> dict[str, object] | None:
    """The most recent report the runner wrote, if any."""
    reports = sorted(folder.glob("*/report.json"))
    return json.loads(reports[-1].read_text()) if reports else None


def changed_files(revision_range: str) -> list[str]:
    """Files changed in the given range."""
    output = subprocess.run(  # noqa: S603 - fixed git command, range comes from CI config
        ["git", "diff", "--name-only", revision_range],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in output.stdout.splitlines() if line]


def verdict(report: dict[str, object] | None, changed: list[str]) -> tuple[int, str]:
    """Exit code and message for one report and one set of changed files."""
    if report is None:
        return 1, "No evaluation report found; the smoke evaluation didn't run."
    if report.get("label") == "quality run":
        return 0, "The smoke evaluation replayed every response and was held to every threshold."
    touched = sorted(f for f in changed if f.startswith(MEASURED))
    if not touched:
        return 0, (
            f"The smoke evaluation was a harness check ({report.get('cache_misses')} cache "
            "misses), but this change touches nothing it measures."
        )
    listed = "\n  ".join(touched)
    return 1, (
        f"This change touches what the evaluation measures:\n  {listed}\n"
        f"but {report.get('cache_misses')} smoke questions had no recorded response, so "
        "answer quality went unmeasured. Record fresh responses with a model key:\n"
        "  make eval-record\n"
        "and commit testdata/llm_cache with the change."
    )


def main() -> int:
    """Check the newest report against the files changed in the range given."""
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    code, message = verdict(newest_report(), changed_files(sys.argv[1]))
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
