"""Publish a witnessed checkpoint for the replay bundle, for the browser to check.

The site's browser verifier trusts two things: the key built into the page, and a
checkpoint someone outside has witnessed. This writes that checkpoint into
``witness/replay/`` in the repository, where the site fetches it from a second
origin (the raw file on GitHub), not from the site that serves the bundle. With
``--stamp`` it also submits the note to the OpenTimestamps calendars, so anyone can
later prove with the standard ``ots`` tool that it existed by that time.

It picks the newest checkpoint in the bundle that is smaller than the whole log,
so the browser always has a consistency proof to check: from the witnessed size to
the size it is shown now.

Usage::

    python -m tallyproof_pipeline.replay_witness --stamp
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from tallyproof_pipeline.settings import REPO_ROOT

BUNDLE = REPO_ROOT / "frontend" / "public" / "replay"
OUT = REPO_ROOT / "witness" / "replay"


def _checkpoints(bundle: Path) -> list[dict[str, object]]:
    lines = (bundle / "checkpoints.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def choose(bundle: Path, size: int | None = None) -> dict[str, object]:
    """The checkpoint to witness: ``size`` if given, else the newest below the whole log."""
    checkpoints = _checkpoints(bundle)
    if size is not None:
        for checkpoint in checkpoints:
            if checkpoint["tree_size"] == size:
                return checkpoint
        raise ValueError(f"the bundle has no checkpoint at size {size}")
    whole = max(int(str(c["tree_size"])) for c in checkpoints)
    earlier = [c for c in checkpoints if int(str(c["tree_size"])) < whole]
    if not earlier:
        raise ValueError("the bundle has only one checkpoint, so there is nothing to extend")
    return max(earlier, key=lambda c: int(str(c["tree_size"])))


def write(checkpoint: dict[str, object], out: Path, now: datetime | None = None) -> Path:
    """Write the witness export line and the note file; return the note file's path."""
    out.mkdir(parents=True, exist_ok=True)
    size = int(str(checkpoint["tree_size"]))
    note = str(checkpoint["note"])
    record = {
        "exported_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "tree_size": size,
        "note": note,
    }
    (out / "checkpoints.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    note_file = out / f"checkpoint-{size}.note"
    note_file.write_text(note, encoding="utf-8")
    return note_file


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin wrapper
    """Write the replay witness, and stamp it when asked."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--size", type=int, default=None)
    parser.add_argument("--stamp", action="store_true", help="submit to OpenTimestamps")
    args = parser.parse_args(argv)
    checkpoint = choose(args.bundle, args.size)
    note_file = write(checkpoint, args.out)
    print(f"witnessed checkpoint {checkpoint['tree_size']} written to {note_file}")
    if args.stamp:
        from apps.ledger.timestamps import stamp
        from config.env import CheckpointerSettings

        calendars = str(CheckpointerSettings.model_fields["witness_ots_calendars"].default)
        result = stamp(note_file.read_bytes(), note_file, calendars.split(","))
        for path in result.written:
            print(f"timestamp proof {path.name}")
        for calendar, error in result.failed.items():
            print(f"calendar {calendar} failed: {error}")
        return 0 if result.written else 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
