import json

import pytest

from tallyproof_core.checkpoint import CheckpointError, Verifier
from tests.vectors_builder import VECTORS_DIR, build_canonical, build_checkpoints, render


@pytest.mark.parametrize(
    ("filename", "builder"),
    [("canonical.json", build_canonical), ("checkpoint.json", build_checkpoints)],
)
def test_committed_vectors_match_the_core_library(filename, builder):
    committed = (VECTORS_DIR / filename).read_text(encoding="utf-8")
    assert committed == render(builder()), "run `make vectors` and commit the result"


def test_checkpoint_vectors_behave_as_labelled():
    vectors = json.loads((VECTORS_DIR / "checkpoint.json").read_text(encoding="utf-8"))
    verifier = Verifier.from_verifier_key(vectors["verifier_key"])
    checkpoint = verifier.verify_checkpoint(vectors["valid"]["note"])
    assert checkpoint.root_hash.hex() == vectors["valid"]["root_hash_hex"]
    for case in vectors["must_fail"]:
        with pytest.raises(CheckpointError):
            verifier.verify_checkpoint(case["note"])
