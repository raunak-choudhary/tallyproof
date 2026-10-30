"""Sign the replay bundle's totals so the static site can prove them (ADR-0024).

Reads the committed bundle's own records, never gold: the bundle's log and its
witnessed checkpoint must not change. Builds the Merkle-sum tree of the whole
bundle, signs its root with the release key, and writes ``totals.json`` beside the
bundle with a proof for every entity and every agency in it.

The file needs no place in the bundle's manifest: its note is signed by the same
pinned key, and every proof in it is checked against that note in the browser.

Usage::

    python -m tallyproof_pipeline.replay_totals          # make replay-totals
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tallyproof_core.checkpoint import Signer, TotalsNote
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.sum_tree import SumTree, proof_to_json, verify_total
from tallyproof_core.totals import OBLIGATIONS, OUTLAYS, Record, leaves, prefix
from tallyproof_pipeline import keygen
from tallyproof_pipeline.settings import REPO_ROOT

BUNDLE = REPO_ROOT / "frontend" / "public" / "replay"


def read_records(bundle: Path) -> list[Record]:
    """The bundle's records, with leaf hashes computed from their canonical bytes."""
    records = []
    with (bundle / "events.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            canonical = row["canonical"].encode("utf-8")
            document = json.loads(canonical)
            records.append(
                Record(
                    int(row["leaf_index"]),
                    str(document["event_type"]),
                    document.get("payload") or {},
                    leaf_hash(canonical),
                )
            )
    return records


def build(records: Sequence[Record], signer: Signer) -> dict[str, Any]:
    """The totals file: a signed note and a proof for every entity and agency."""
    tree = SumTree(leaves(records))
    root = tree.root()
    note = signer.sign_totals(TotalsNote(signer.name, len(records), root))
    agencies = sorted(
        {leaf.key[1] for leaf in leaves(records) if leaf.key[1]},
    )
    entries = []
    for entity in (OBLIGATIONS, OUTLAYS):
        for agency in (None, *agencies):
            proof = tree.prove(prefix(entity, agency))
            proven = verify_total(proof, root)
            if proven is None:
                raise RuntimeError(f"a fresh proof failed for {entity} {agency}")
            if agency is not None and proven.count == 0:
                continue
            entries.append(
                {
                    "entity": entity,
                    "agency": agency,
                    "total_cents": str(proven.total),
                    "count": proven.count,
                    "proof": proof_to_json(proof),
                }
            )
    return {"tree_size": len(records), "records": tree.size, "note": note, "totals": entries}


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Write totals.json for the committed replay bundle."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--key-class", default="rel", choices=keygen.KEY_CLASSES)
    args = parser.parse_args()
    manifest = json.loads((args.bundle / "manifest.json").read_text(encoding="utf-8"))
    signer = keygen.load(args.key_class)
    if signer.name != manifest["origin"]:
        raise SystemExit(f"the {args.key_class} key signs {signer.name}, not {manifest['origin']}")
    records = read_records(args.bundle)
    if len(records) != manifest["tree_size"]:
        raise SystemExit("the bundle's events don't match its manifest")
    contents = build(records, signer)
    (args.bundle / "totals.json").write_text(json.dumps(contents, indent=1) + "\n", "utf-8")
    print(f"signed totals for {contents['records']} records, {len(contents['totals'])} proofs")


if __name__ == "__main__":  # pragma: no cover
    main()
