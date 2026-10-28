import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import consistency_proof, root, verify_consistency
from tests.conftest import VECTORS_DIR

VECTORS = json.loads((VECTORS_DIR / "merkle_reference.json").read_text())
LEAVES = [leaf_hash(bytes.fromhex(h)) for h in VECTORS["leaf_inputs_hex"]]
ROOTS = [bytes.fromhex(h) for h in VECTORS["root_hashes_by_size_hex"]]


@pytest.mark.parametrize("case", VECTORS["consistency_proofs"])
def test_consistency_proof_matches_reference(case):
    proof = consistency_proof(LEAVES[: case["size2"]], case["size1"])
    assert [p.hex() for p in proof] == case["proof_hex"]


@pytest.mark.parametrize("case", VECTORS["consistency_proofs"])
def test_reference_consistency_proof_verifies(case):
    first, second = case["size1"], case["size2"]
    proof = [bytes.fromhex(p) for p in case["proof_hex"]]
    assert verify_consistency(first, second, ROOTS[first], ROOTS[second], proof)


@pytest.mark.parametrize(
    ("first", "second"), [(m, n) for n in range(1, 9) for m in range(1, n + 1)]
)
def test_every_reference_size_pair_is_consistent(first, second):
    proof = consistency_proof(LEAVES[:second], first)
    assert verify_consistency(first, second, ROOTS[first], ROOTS[second], proof)


def test_consistency_proof_rejects_invalid_sizes():
    with pytest.raises(ValueError, match="first size"):
        consistency_proof(LEAVES[:4], 5)
    with pytest.raises(ValueError, match="first size"):
        consistency_proof(LEAVES[:4], 0)


leaf_lists = st.lists(st.binary(max_size=40), min_size=1, max_size=70, unique=True).map(
    lambda items: [leaf_hash(item) for item in items]
)


@given(leaves=leaf_lists, data=st.data())
def test_any_prefix_is_consistent_with_the_full_log(leaves, data):
    first = data.draw(st.integers(1, len(leaves)))
    proof = consistency_proof(leaves, first)
    assert verify_consistency(first, len(leaves), root(leaves[:first]), root(leaves), proof)


@given(leaves=leaf_lists.filter(lambda leaves: len(leaves) > 1), data=st.data())
def test_rewriting_history_breaks_consistency(leaves, data):
    first = data.draw(st.integers(1, len(leaves) - 1))
    old_root = root(leaves[:first])
    # An attacker rewrites one record that the old checkpoint already covered.
    victim = data.draw(st.integers(0, first - 1))
    rewritten = list(leaves)
    rewritten[victim] = leaf_hash(b"forged record" + leaves[victim])
    proof = consistency_proof(rewritten, first)
    assert not verify_consistency(first, len(rewritten), old_root, root(rewritten), proof)


@given(leaves=leaf_lists.filter(lambda leaves: len(leaves) > 1), data=st.data())
def test_any_tampered_proof_element_fails(leaves, data):
    first = data.draw(st.integers(1, len(leaves) - 1))
    proof = consistency_proof(leaves, first)
    position = data.draw(st.integers(0, len(proof) - 1))
    bit = data.draw(st.integers(0, 255))
    tampered = bytearray(proof[position])
    tampered[bit // 8] ^= 1 << (bit % 8)
    proof[position] = bytes(tampered)
    assert not verify_consistency(first, len(leaves), root(leaves[:first]), root(leaves), proof)


def test_malformed_inputs_fail_closed():
    good = consistency_proof(LEAVES, 3)
    assert not verify_consistency(5, 3, ROOTS[5], ROOTS[3], good)  # shrinking log
    assert not verify_consistency(0, 8, ROOTS[0], ROOTS[8], [])  # empty first tree
    assert not verify_consistency(3, 8, ROOTS[3], ROOTS[8], [])  # missing proof
    assert not verify_consistency(3, 8, ROOTS[3], ROOTS[8], [b"short"])  # bad hash length
    assert not verify_consistency(3, 8, ROOTS[3], ROOTS[8], [*good, good[0]])  # too long
    assert not verify_consistency(8, 8, ROOTS[8], ROOTS[8], [ROOTS[8]])  # equal sizes need no proof
    assert not verify_consistency(8, 8, ROOTS[8], ROOTS[7], [])  # equal sizes, different roots
