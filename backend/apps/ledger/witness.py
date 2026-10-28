"""Check exported checkpoints against the pinned key and the current log.

Each exported checkpoint must carry a valid signature from the pinned key, sizes
must only grow, and the current log must still produce every exported root. A
failure on the last check means stored history was rewritten after the
checkpoint was witnessed (tamper ladder level 3).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from tallyproof_core.checkpoint import CheckpointError, Verifier
from tallyproof_core.log_tree import LogTree


@dataclass
class WitnessReport:
    """Result of checking a witness file."""

    checked: int = 0
    timestamped: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when every exported checkpoint checked out."""
        return not self.problems


def verify(path: Path, verifier: Verifier, tree: LogTree) -> WitnessReport:
    """Verify every checkpoint in the witness file at ``path``."""
    report = WitnessReport()
    if not path.exists():
        report.problems.append(f"no witness file at {path}")
        return report
    previous = 0
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        record = json.loads(line)
        try:
            checkpoint = verifier.verify_checkpoint(record["note"])
        except CheckpointError as error:
            report.problems.append(f"line {number}: signature check failed: {error}")
            continue
        size = checkpoint.tree_size
        if size < previous:
            report.problems.append(f"line {number}: size {size} is smaller than {previous}")
        previous = max(previous, size)
        if size > tree.size:
            report.problems.append(f"line {number}: checkpoint {size} is past the log's end")
        elif tree.root(size) != checkpoint.root_hash:
            report.problems.append(f"line {number}: the log no longer matches checkpoint {size}")
        report.checked += 1
        if any(path.parent.glob(f"checkpoint-{size}.note.*.ots")):
            report.timestamped += 1
    return report
