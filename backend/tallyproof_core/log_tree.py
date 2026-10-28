"""A Merkle log held in memory, fast enough to serve proofs over millions of leaves.

:mod:`tallyproof_core.merkle` is the reference implementation: short, recursive,
and easy to check against RFC 9162, but it rehashes the whole tree on every
call. :class:`LogTree` computes exactly the same roots and proofs while doing
about ``log n`` hash operations per call once warm.

Two facts make that possible:

- Every subtree the RFC 9162 algorithms visit is either the incomplete right
  edge of the tree or a complete subtree whose size is a power of two and whose
  start is a multiple of that size.
- A complete subtree's hash never changes as the log grows.

So complete subtrees of at least ``cache_min`` leaves are cached by position and
reused by every later root and proof, at any tree size. Leaf hashes live in one
flat buffer: 32 bytes per leaf, so a million leaves take 32 MB.
"""

from tallyproof_core.hashing import EMPTY_ROOT, HASH_SIZE, node_hash


def _split_point(size: int) -> int:
    return 1 << ((size - 1).bit_length() - 1)


class LogTree:
    """An append-only list of leaf hashes with cached subtree hashes."""

    def __init__(self, cache_min: int = 256) -> None:
        """Create an empty log.

        Args:
            cache_min: Smallest complete subtree, in leaves, whose hash is cached.
                Must be a power of two. Smaller values use more memory and fewer
                hash operations.
        """
        if cache_min < 1 or cache_min & (cache_min - 1):
            raise ValueError("cache_min must be a power of two")
        self._leaves = bytearray()
        self._cache: dict[tuple[int, int], bytes] = {}
        self._cache_min = cache_min

    @property
    def size(self) -> int:
        """Number of leaves in the log."""
        return len(self._leaves) // HASH_SIZE

    def append(self, leaf_hash: bytes) -> int:
        """Add one leaf hash and return its index."""
        if len(leaf_hash) != HASH_SIZE:
            raise ValueError(f"leaf hashes are {HASH_SIZE} bytes")
        self._leaves += leaf_hash
        return self.size - 1

    def leaf(self, index: int) -> bytes:
        """Return the leaf hash at ``index``."""
        if not 0 <= index < self.size:
            raise IndexError(f"leaf {index} is outside a log of size {self.size}")
        return bytes(self._leaves[index * HASH_SIZE : (index + 1) * HASH_SIZE])

    def _hash(self, start: int, end: int) -> bytes:
        """Merkle tree hash of the leaves ``[start, end)``."""
        count = end - start
        if count == 1:
            return self.leaf(start)
        complete = count & (count - 1) == 0
        if complete and count >= self._cache_min:
            cached = self._cache.get((start, count))
            if cached is not None:
                return cached
        k = _split_point(count)
        digest = node_hash(self._hash(start, start + k), self._hash(start + k, end))
        if complete and count >= self._cache_min:
            self._cache[(start, count)] = digest
        return digest

    def _check_size(self, tree_size: int | None) -> int:
        size = self.size if tree_size is None else tree_size
        if not 0 <= size <= self.size:
            raise ValueError(f"tree size {size} is outside a log of size {self.size}")
        return size

    def root(self, tree_size: int | None = None) -> bytes:
        """Root hash of the first ``tree_size`` leaves (default: all of them)."""
        size = self._check_size(tree_size)
        return EMPTY_ROOT if size == 0 else self._hash(0, size)

    def inclusion_proof(self, index: int, tree_size: int | None = None) -> list[bytes]:
        """Audit path for leaf ``index`` in the tree of the first ``tree_size`` leaves."""
        size = self._check_size(tree_size)
        if not 0 <= index < size:
            raise ValueError(f"index {index} is outside a tree of size {size}")
        path: list[bytes] = []
        start, end = 0, size
        # Walk down from the root, collecting siblings; the RFC lists them leaf first.
        while end - start > 1:
            k = _split_point(end - start)
            if index < start + k:
                path.append(self._hash(start + k, end))
                end = start + k
            else:
                path.append(self._hash(start, start + k))
                start += k
        path.reverse()
        return path

    def consistency_proof(self, first_size: int, tree_size: int | None = None) -> list[bytes]:
        """Proof that the first ``first_size`` leaves are a prefix of the larger tree."""
        size = self._check_size(tree_size)
        if not 0 < first_size <= size:
            raise ValueError(f"first size {first_size} must be between 1 and {size}")
        path: list[bytes] = []
        start, end, m, complete = 0, size, first_size, True
        # Iterative RFC 9162 SUBPROOF; siblings are collected top down, then reversed.
        while m != end - start:
            k = _split_point(end - start)
            if m <= k:
                path.append(self._hash(start + k, end))
                end = start + k
            else:
                path.append(self._hash(start, start + k))
                start, m, complete = start + k, m - k, False
        if not complete:
            path.append(self._hash(start, end))
        path.reverse()
        return path
