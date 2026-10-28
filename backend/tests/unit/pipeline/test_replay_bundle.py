import base64
import hashlib
import json
import stat
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tallyproof_core.checkpoint import Signer, Verifier
from tallyproof_core.events import EventEnvelope
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import inclusion_proof, verify_inclusion
from tallyproof_pipeline import keygen
from tallyproof_pipeline.gold import conform
from tallyproof_pipeline.replay_bundle import export_bundle

SIGNER = Signer(
    "test.tallyproof.dev/log/v1",
    Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"bundle test key").digest()),
)


def events(count: int = 10) -> list[EventEnvelope]:
    out = []
    for i in range(count):
        day = date(2025, 1, 1) + timedelta(days=i)
        out.append(
            conform(
                {
                    "contract_transaction_unique_key": f"T{i}",
                    "contract_award_unique_key": f"CONT_AWD_A{i}",
                    "award_id_piid": f"PIID{i}",
                    "modification_number": "0",
                    "federal_action_obligation": Decimal("100.00") * (i + 1),
                    "action_date": day,
                    "last_modified_date": datetime.combine(day, datetime.min.time()),
                    "awarding_agency_name": "Department of Energy",
                    "recipient_uei": "ZQGGHJH74DW7",
                },
                seed=1,
            )
        )
    return out


def test_bundle_verifies_end_to_end_from_its_own_files(tmp_path):
    summary = export_bundle(events(), SIGNER, tmp_path, checkpoint_every=4)
    assert (summary.events, summary.checkpoints) == (10, 3)  # sizes 4, 8, 10

    verifier = Verifier.from_verifier_key(
        json.loads((tmp_path / "log-key.json").read_text())["verifier_key"]
    )
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    leaves = [leaf_hash(r["canonical"].encode()) for r in records]
    final = verifier.verify_checkpoint(
        json.loads((tmp_path / "checkpoints.jsonl").read_text().splitlines()[-1])["note"]
    )
    assert final.tree_size == 10
    for index in range(10):
        proof = inclusion_proof(leaves, index)
        assert verify_inclusion(leaves[index], index, 10, proof, final.root_hash)


def test_manifest_lists_file_hashes_and_its_signature_verifies(tmp_path):
    export_bundle(events(), SIGNER, tmp_path, parameters={"overlay_seed": 42})
    manifest_text = (tmp_path / "manifest.json").read_text()
    manifest = json.loads(manifest_text)
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest
    signed = Verifier.from_verifier_key(SIGNER.verifier_key()).verify_note(
        (tmp_path / "manifest.sig").read_text()
    )
    assert hashlib.sha256(manifest_text.encode()).hexdigest() in signed
    assert manifest["parameters"] == {"overlay_seed": 42}


def test_same_input_gives_byte_identical_bundles(tmp_path):
    export_bundle(events(), SIGNER, tmp_path / "a")
    export_bundle(events(), SIGNER, tmp_path / "b")
    for name in ("events.jsonl", "checkpoints.jsonl", "manifest.json", "manifest.sig"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_tampering_with_an_exported_event_breaks_its_proof(tmp_path):
    export_bundle(events(), SIGNER, tmp_path)
    records = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    leaves = [leaf_hash(r["canonical"].encode()) for r in records]
    checkpoint = Verifier.from_verifier_key(SIGNER.verifier_key()).verify_checkpoint(
        json.loads((tmp_path / "checkpoints.jsonl").read_text().splitlines()[-1])["note"]
    )
    forged = records[3]["canonical"].replace('"400.00"', '"900.00"')
    assert forged != records[3]["canonical"]
    proof = inclusion_proof(leaves, 3)
    assert not verify_inclusion(leaf_hash(forged.encode()), 3, 10, proof, checkpoint.root_hash)


def test_empty_or_duplicated_input_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        export_bundle([], SIGNER, tmp_path)
    one = events(1)
    with pytest.raises(ValueError, match="unique"):
        export_bundle([*one, *one], SIGNER, tmp_path)


def test_keygen_writes_an_owner_only_key_and_refuses_to_overwrite(tmp_path):
    signer = keygen.generate("dev", tmp_path)
    path = keygen.key_path("dev", tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert keygen.load("dev", tmp_path).public_key == signer.public_key
    assert signer.name == "dev.tallyproof.dev/log/v1"
    with pytest.raises(FileExistsError, match="rotate"):
        keygen.generate("dev", tmp_path)
    with pytest.raises(ValueError, match="unknown key class"):
        keygen.generate("prod", tmp_path)


def test_generated_key_file_uses_the_scannable_prefix(tmp_path):
    keygen.generate("rel", tmp_path)
    text = keygen.key_path("rel", tmp_path).read_text()
    assert text.startswith("tallyproof-ed25519-private-v1:")
    assert len(base64.b64decode(text.split(":", 1)[1])) == 32
