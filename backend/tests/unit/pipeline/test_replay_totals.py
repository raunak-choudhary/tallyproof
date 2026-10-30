"""Signed totals for the replay bundle: every proof checks against the signed note."""

import json

from tallyproof_core.checkpoint import Verifier
from tallyproof_core.sum_tree import proof_from_json, verify_total
from tallyproof_pipeline.replay_totals import BUNDLE, build, read_records
from tests.unit.pipeline.test_replay_bundle import SIGNER


def test_every_proof_in_the_file_verifies_against_its_note() -> None:
    records = read_records(BUNDLE)
    contents = build(records, SIGNER)
    note = Verifier.from_verifier_key(SIGNER.verifier_key()).verify_totals(contents["note"])
    assert note.tree_size == len(records) == contents["tree_size"]
    for entry in contents["totals"]:
        proven = verify_total(proof_from_json(entry["proof"]), note.root_hash)
        assert proven is not None
        assert (str(proven.total), proven.count) == (entry["total_cents"], entry["count"])


def test_agency_totals_add_up_to_no_more_than_the_entity_total() -> None:
    contents = build(read_records(BUNDLE), SIGNER)
    whole = next(
        t for t in contents["totals"] if t["entity"] == "obligations" and t["agency"] is None
    )
    agencies = [t for t in contents["totals"] if t["entity"] == "obligations" and t["agency"]]
    assert agencies
    assert sum(t["count"] for t in agencies) <= whole["count"]


def test_the_committed_totals_verify_against_the_bundles_own_key() -> None:
    key = json.loads((BUNDLE / "log-key.json").read_text(encoding="utf-8"))["verifier_key"]
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    committed = json.loads((BUNDLE / "totals.json").read_text(encoding="utf-8"))
    note = Verifier.from_verifier_key(key).verify_totals(committed["note"])
    assert note.tree_size == manifest["tree_size"]
    for entry in committed["totals"]:
        proven = verify_total(proof_from_json(entry["proof"]), note.root_hash)
        assert proven is not None
        assert (str(proven.total), proven.count) == (entry["total_cents"], entry["count"])
