import hashlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tallyproof_core import merkle
from tallyproof_core.hashing import EMPTY_ROOT, leaf_hash
from tallyproof_core.log_tree import LogTree


def leaves(count: int) -> list[bytes]:
    return [leaf_hash(i.to_bytes(4, "big")) for i in range(count)]


def tree_of(hashes: list[bytes], cache_min: int = 2) -> LogTree:
    tree = LogTree(cache_min=cache_min)
    for h in hashes:
        tree.append(h)
    return tree


sizes = st.integers(min_value=1, max_value=300)


@given(sizes, st.sampled_from([1, 2, 4, 64]))
def test_roots_match_the_reference_at_every_prefix(size, cache_min):
    hashes = leaves(size)
    tree = tree_of(hashes, cache_min)
    for n in {1, size // 3 or 1, size // 2 or 1, size}:
        assert tree.root(n) == merkle.root(hashes[:n])


@given(sizes, st.data())
def test_inclusion_proofs_match_the_reference(size, data):
    hashes = leaves(size)
    tree = tree_of(hashes)
    n = data.draw(st.integers(1, size))
    index = data.draw(st.integers(0, n - 1))
    proof = tree.inclusion_proof(index, n)
    assert proof == merkle.inclusion_proof(hashes[:n], index)
    assert merkle.verify_inclusion(hashes[index], index, n, proof, tree.root(n))


@given(sizes, st.data())
def test_consistency_proofs_match_the_reference(size, data):
    hashes = leaves(size)
    tree = tree_of(hashes)
    second = data.draw(st.integers(1, size))
    first = data.draw(st.integers(1, second))
    proof = tree.consistency_proof(first, second)
    assert proof == merkle.consistency_proof(hashes[:second], first)
    assert merkle.verify_consistency(first, second, tree.root(first), tree.root(second), proof)


def test_cached_hashes_stay_valid_as_the_log_grows():
    hashes = leaves(1000)
    tree = tree_of(hashes[:600], cache_min=4)
    early = tree.root(512)
    for h in hashes[600:]:
        tree.append(h)
    assert tree.root(512) == early == merkle.root(hashes[:512])
    assert tree.root() == merkle.root(hashes)


def test_empty_tree_and_bad_arguments():
    tree = LogTree()
    assert tree.root() == EMPTY_ROOT
    with pytest.raises(ValueError, match="power of two"):
        LogTree(cache_min=3)
    with pytest.raises(ValueError, match="32 bytes"):
        tree.append(b"short")
    tree.append(hashlib.sha256(b"x").digest())
    with pytest.raises(ValueError, match="outside"):
        tree.root(2)
    with pytest.raises(ValueError, match="outside"):
        tree.inclusion_proof(1)
    with pytest.raises(ValueError, match="between"):
        tree.consistency_proof(0)
    with pytest.raises(IndexError):
        tree.leaf(5)
