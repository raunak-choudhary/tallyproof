import hashlib
import json

import pytest

from tallyproof_core.hashing import EMPTY_ROOT, HASH_SIZE, leaf_hash, node_hash
from tests.conftest import VECTORS_DIR

VECTORS = json.loads((VECTORS_DIR / "merkle_reference.json").read_text())


def test_leaf_hash_matches_reference_single_leaf_root():
    # A one-leaf tree's root is the hash of that leaf.
    assert leaf_hash(b"").hex() == VECTORS["root_hashes_by_size_hex"][1]


def test_empty_root_is_hash_of_empty_string():
    assert EMPTY_ROOT.hex() == VECTORS["root_hashes_by_size_hex"][0]


def test_leaf_and_node_hashes_are_domain_separated():
    data = b"\x00" * 64
    assert leaf_hash(data) != hashlib.sha256(data).digest()
    assert node_hash(data[:32], data[32:]) != leaf_hash(data)


def test_node_hash_rejects_wrong_length_children():
    with pytest.raises(ValueError, match="32 bytes"):
        node_hash(b"short", b"\x00" * HASH_SIZE)
