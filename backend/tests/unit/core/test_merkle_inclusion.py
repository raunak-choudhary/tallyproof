import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import inclusion_proof, root, verify_inclusion
from tests.conftest import VECTORS_DIR

VECTORS = json.loads((VECTORS_DIR / "merkle_reference.json").read_text())
LEAVES = [leaf_hash(bytes.fromhex(h)) for h in VECTORS["leaf_inputs_hex"]]

leaf_lists = st.lists(st.binary(max_size=40), min_size=1, max_size=70).map(
    lambda items: [leaf_hash(item) for item in items]
)


@pytest.mark.parametrize("size", range(len(VECTORS["root_hashes_by_size_hex"])))
def test_root_matches_reference_for_every_size(size):
    assert root(LEAVES[:size]).hex() == VECTORS["root_hashes_by_size_hex"][size]


@pytest.mark.parametrize("case", VECTORS["inclusion_proofs"])
def test_inclusion_proof_matches_reference(case):
    proof = inclusion_proof(LEAVES[: case["size"]], case["index"])
    assert [p.hex() for p in proof] == case["proof_hex"]


@pytest.mark.parametrize("case", VECTORS["inclusion_proofs"])
def test_reference_inclusion_proof_verifies(case):
    size, index = case["size"], case["index"]
    proof = [bytes.fromhex(p) for p in case["proof_hex"]]
    expected_root = bytes.fromhex(VECTORS["root_hashes_by_size_hex"][size])
    assert verify_inclusion(LEAVES[index], index, size, proof, expected_root)


def test_inclusion_proof_rejects_index_outside_tree():
    with pytest.raises(ValueError, match="outside"):
        inclusion_proof(LEAVES[:3], 3)


@given(leaves=leaf_lists, data=st.data())
def test_every_leaf_has_a_valid_inclusion_proof(leaves, data):
    index = data.draw(st.integers(0, len(leaves) - 1))
    proof = inclusion_proof(leaves, index)
    assert verify_inclusion(leaves[index], index, len(leaves), proof, root(leaves))


@given(leaves=leaf_lists, data=st.data())
def test_any_tampered_leaf_fails_verification(leaves, data):
    index = data.draw(st.integers(0, len(leaves) - 1))
    proof = inclusion_proof(leaves, index)
    bit = data.draw(st.integers(0, 255))
    tampered = bytearray(leaves[index])
    tampered[bit // 8] ^= 1 << (bit % 8)
    assert not verify_inclusion(bytes(tampered), index, len(leaves), proof, root(leaves))


@given(leaves=leaf_lists.filter(lambda leaves: len(leaves) > 1), data=st.data())
def test_any_tampered_proof_element_fails_verification(leaves, data):
    index = data.draw(st.integers(0, len(leaves) - 1))
    proof = inclusion_proof(leaves, index)
    position = data.draw(st.integers(0, len(proof) - 1))
    bit = data.draw(st.integers(0, 255))
    tampered = bytearray(proof[position])
    tampered[bit // 8] ^= 1 << (bit % 8)
    proof[position] = bytes(tampered)
    assert not verify_inclusion(leaves[index], index, len(leaves), proof, root(leaves))


distinct_leaf_lists = st.lists(st.binary(max_size=40), min_size=2, max_size=70, unique=True).map(
    lambda items: [leaf_hash(item) for item in items]
)


# Identical leaves are interchangeable by definition, so this only holds for
# distinct leaves. Ledger leaves are always distinct: each carries a unique event ID.
@given(leaves=distinct_leaf_lists, data=st.data())
def test_proof_does_not_verify_at_a_different_index(leaves, data):
    index = data.draw(st.integers(0, len(leaves) - 1))
    other = data.draw(st.integers(0, len(leaves) - 1).filter(lambda i: i != index))
    proof = inclusion_proof(leaves, index)
    assert not verify_inclusion(leaves[index], other, len(leaves), proof, root(leaves))


def test_malformed_inputs_fail_closed_instead_of_raising():
    good_root = root(LEAVES)
    assert not verify_inclusion(LEAVES[0], 8, 8, [], good_root)  # index past the end
    assert not verify_inclusion(LEAVES[0], 0, 0, [], good_root)  # empty tree
    assert not verify_inclusion(LEAVES[0], 0, 8, [b"short"], good_root)  # bad hash length
    proof = inclusion_proof(LEAVES, 0)
    assert not verify_inclusion(LEAVES[0], 0, 8, [*proof, proof[0]], good_root)  # too long
