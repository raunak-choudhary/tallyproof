"""Append-only Merkle log: roots, inclusion proofs, and consistency proofs.

Implements the tree described in RFC 9162, section 2.1. Trees of any size are
supported: when a level has an odd number of nodes, the tree splits at the
largest power of two smaller than its size instead of duplicating the last
node, which avoids the ambiguity behind Bitcoin's CVE-2012-2459.

Functions here take leaf hashes, not raw leaf data, so callers hash each leaf
once with :func:`tallyproof_core.hashing.leaf_hash` and reuse it.

Verification functions never raise on bad input. A malformed proof is a failed
proof, and they return ``False``.
"""

from collections.abc import Sequence

from tallyproof_core.hashing import EMPTY_ROOT, HASH_SIZE, node_hash


def _split_point(size: int) -> int:
    """Return the largest power of two strictly smaller than ``size`` (size > 1)."""
    return 1 << ((size - 1).bit_length() - 1)


def root(leaf_hashes: Sequence[bytes]) -> bytes:
    """Compute the Merkle tree hash of a list of leaf hashes.

    Args:
        leaf_hashes: Leaf hashes in log order.

    Returns:
        The 32-byte root hash. An empty tree hashes to SHA-256 of the empty string.
    """
    size = len(leaf_hashes)
    if size == 0:
        return EMPTY_ROOT
    if size == 1:
        return leaf_hashes[0]
    k = _split_point(size)
    return node_hash(root(leaf_hashes[:k]), root(leaf_hashes[k:]))


def inclusion_proof(leaf_hashes: Sequence[bytes], index: int) -> list[bytes]:
    """Build the audit path proving one leaf is in the tree.

    Args:
        leaf_hashes: All leaf hashes of the tree, in log order.
        index: Position of the leaf to prove.

    Returns:
        Sibling hashes from the leaf up to the root (RFC 9162 PATH).

    Raises:
        ValueError: If ``index`` is outside the tree.
    """
    size = len(leaf_hashes)
    if not 0 <= index < size:
        raise ValueError(f"index {index} is outside a tree of size {size}")
    if size == 1:
        return []
    k = _split_point(size)
    if index < k:
        return [*inclusion_proof(leaf_hashes[:k], index), root(leaf_hashes[k:])]
    return [*inclusion_proof(leaf_hashes[k:], index - k), root(leaf_hashes[:k])]


def verify_inclusion(
    leaf: bytes,
    index: int,
    tree_size: int,
    proof: Sequence[bytes],
    expected_root: bytes,
) -> bool:
    """Check an inclusion proof (RFC 9162, section 2.1.3.2).

    Args:
        leaf: The leaf hash being proved.
        index: The leaf's position in the tree.
        tree_size: Number of leaves in the tree the root describes.
        proof: The audit path returned by :func:`inclusion_proof`.
        expected_root: The trusted root hash, for example from a signed checkpoint.

    Returns:
        True only if the proof reproduces ``expected_root`` exactly.
    """
    if not 0 <= index < tree_size:
        return False
    if len(leaf) != HASH_SIZE or any(len(p) != HASH_SIZE for p in proof):
        return False

    fn, sn = index, tree_size - 1
    computed = leaf
    for sibling in proof:
        if sn == 0:
            return False  # proof is longer than the tree is tall
        if fn & 1 or fn == sn:
            computed = node_hash(sibling, computed)
            # A right edge with no sibling at this level: climb until there is one.
            while not fn & 1 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            computed = node_hash(computed, sibling)
        fn >>= 1
        sn >>= 1
    return sn == 0 and computed == expected_root
