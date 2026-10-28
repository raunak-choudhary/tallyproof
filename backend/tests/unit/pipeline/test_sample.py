import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tallyproof_core.checkpoint import Signer, Verifier
from tallyproof_core.merkle import inclusion_proof, verify_inclusion
from tallyproof_pipeline.gold import read_events
from tallyproof_pipeline.replay_bundle import export_bundle
from tallyproof_pipeline.silver import PII_COLUMNS

SAMPLE = Path(__file__).resolve().parents[4] / "testdata" / "sample" / "gold_events_sample.jsonl.gz"


def test_real_sample_events_validate_and_carry_no_personal_data():
    events = list(read_events(SAMPLE))
    assert len(events) == 2000
    text = " ".join(e.model_dump_json() for e in events)
    for column in PII_COLUMNS:
        assert column not in text
    assert len({e.event_id for e in events}) == 2000


def test_real_sample_builds_a_bundle_whose_proofs_verify(tmp_path):
    signer = Signer(
        "test.tallyproof.dev/log/v1",
        Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"sample test").digest()),
    )
    events = list(read_events(SAMPLE))
    summary = export_bundle(events, signer, tmp_path)
    leaves = [e.leaf_hash() for e in events]
    last = json.loads((tmp_path / "checkpoints.jsonl").read_text().splitlines()[-1])
    checkpoint = Verifier.from_verifier_key(signer.verifier_key()).verify_checkpoint(last["note"])
    assert checkpoint.tree_size == summary.events == 2000
    for index in (0, 999, 1999):
        proof = inclusion_proof(leaves, index)
        assert verify_inclusion(leaves[index], index, 2000, proof, checkpoint.root_hash)
