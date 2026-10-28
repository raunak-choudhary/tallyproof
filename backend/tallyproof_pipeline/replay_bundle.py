"""Export a signed, self-verifying bundle of a real run for the static demo site.

The public demo has no backend. Instead it loads a bundle produced here from real
gold events, and the browser recomputes every leaf hash, every proof, and every
signature check itself. Nothing in the bundle says "verified".

Bundle contents:

- ``events.jsonl``: one line per leaf in log order: leaf index, event ID, and the
  exact canonical JSON that was hashed.
- ``checkpoints.jsonl``: a signed checkpoint every ``checkpoint_every`` leaves and
  one at the end.
- ``log-key.json``: the public verifier key and log origin.
- ``manifest.json``: the SHA-256 of every other file, plus the run's parameters.
- ``manifest.sig``: the manifest's SHA-256 signed as a note, so the bundle as a
  whole can be checked against the pinned key before anything else is trusted.

Given the same events and key, the output is byte for byte the same.

Usage::

    python -m tallyproof_pipeline.replay_bundle
"""

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tallyproof_core.checkpoint import Checkpoint, Signer
from tallyproof_core.events import EventEnvelope
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import root
from tallyproof_pipeline import keygen
from tallyproof_pipeline.gold import read_events
from tallyproof_pipeline.settings import REPO_ROOT, get_settings

BUNDLE_VERSION = 1


@dataclass(frozen=True)
class BundleSummary:
    """What was exported."""

    events: int
    checkpoints: int
    root_hash_hex: str


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def export_bundle(
    events: Sequence[EventEnvelope],
    signer: Signer,
    out_dir: Path,
    *,
    checkpoint_every: int = 256,
    parameters: dict[str, object] | None = None,
) -> BundleSummary:
    """Build the Merkle log over ``events`` and write the signed bundle.

    Args:
        events: Events in the order they enter the log.
        signer: Signs checkpoints and the manifest; its key name is the log origin.
        out_dir: Directory to write the bundle into.
        checkpoint_every: Leaves between intermediate checkpoints.
        parameters: Run details recorded in the manifest, such as the seed.

    Raises:
        ValueError: If there are no events or two events share an ID.
    """
    if not events:
        raise ValueError("a bundle needs at least one event")
    if len({e.event_id for e in events}) != len(events):
        raise ValueError("event IDs must be unique within a bundle")
    out_dir.mkdir(parents=True, exist_ok=True)

    lines, leaves = [], []
    for index, event in enumerate(events):
        canonical = event.canonical_bytes()
        leaves.append(leaf_hash(canonical))
        record = {"leaf_index": index, "event_id": event.event_id, "canonical": canonical.decode()}
        lines.append(json.dumps(record, ensure_ascii=False, sort_keys=True))

    sizes = [*range(checkpoint_every, len(leaves), checkpoint_every), len(leaves)]
    checkpoints = []
    for size in sizes:
        checkpoint = Checkpoint(signer.name, size, root(leaves[:size]))
        checkpoints.append(
            json.dumps({"tree_size": size, "note": signer.sign_checkpoint(checkpoint)})
        )

    hashes = {
        "events.jsonl": _write(out_dir / "events.jsonl", "\n".join(lines) + "\n"),
        "checkpoints.jsonl": _write(out_dir / "checkpoints.jsonl", "\n".join(checkpoints) + "\n"),
        "log-key.json": _write(
            out_dir / "log-key.json",
            json.dumps({"origin": signer.name, "verifier_key": signer.verifier_key()}, indent=2)
            + "\n",
        ),
    }
    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "origin": signer.name,
        "tree_size": len(leaves),
        "root_hash_hex": root(leaves).hex(),
        "files": hashes,
        "parameters": parameters or {},
    }
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_hash = _write(out_dir / "manifest.json", manifest_text)
    (out_dir / "manifest.sig").write_text(
        signer.sign_note(f"tallyproof replay bundle\nmanifest sha256 {manifest_hash}\n"),
        encoding="utf-8",
    )
    return BundleSummary(len(leaves), len(checkpoints), root(leaves).hex())


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Export the first N gold events as the demo bundle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=2000, help="events to include")
    parser.add_argument("--key-class", default="rel", choices=keygen.KEY_CLASSES)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "replay")
    args = parser.parse_args()
    settings = get_settings()
    events = []
    for event in read_events(settings.gold_dir / "events.jsonl.gz"):
        events.append(event)
        if len(events) == args.events:
            break
    summary = export_bundle(
        events,
        keygen.load(args.key_class),
        args.out,
        parameters={"overlay_seed": settings.overlay_seed, "source": "USAspending FY contracts"},
    )
    print(summary)


if __name__ == "__main__":  # pragma: no cover
    main()
