"""Leaf and interior node hashing for the Merkle log (RFC 9162, section 2.1.1).

Leaves and interior nodes are hashed with different one-byte prefixes. Without
that separation, an attacker could present an interior node as if it were a
leaf and forge an inclusion proof (a second-preimage attack).
"""

import hashlib

HASH_SIZE = 32
"""Length in bytes of every hash in the log (SHA-256)."""

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"

EMPTY_ROOT = hashlib.sha256(b"").digest()
"""Root hash of a tree with no leaves."""


def leaf_hash(data: bytes) -> bytes:
    """Hash one leaf: SHA-256(0x00 || data).

    Args:
        data: The leaf's canonical bytes.

    Returns:
        The 32-byte leaf hash.
    """
    return hashlib.sha256(LEAF_PREFIX + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """Hash an interior node: SHA-256(0x01 || left || right).

    Args:
        left: Hash of the left subtree.
        right: Hash of the right subtree.

    Returns:
        The 32-byte node hash.

    Raises:
        ValueError: If either child is not exactly 32 bytes.
    """
    if len(left) != HASH_SIZE or len(right) != HASH_SIZE:
        raise ValueError(f"child hashes must be {HASH_SIZE} bytes")
    return hashlib.sha256(NODE_PREFIX + left + right).digest()
