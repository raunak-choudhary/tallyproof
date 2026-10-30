"""A sorted Merkle-sum tree: prove a total without listing the records behind it.

Each leaf is one record: a key, an amount in minor units (cents), and the record's
leaf hash in the Merkle log. Leaves are sorted by key, and the tree has the same
shape as the log (RFC 9162: split at the largest power of two below the size).
Every node commits to four things besides its children: the sum of its leaves,
how many there are, and its smallest and largest key.

Keys are tuples of strings, such as ``("obligations", "Department of Energy",
"2024", "00000000000000001234")``. Because leaves are sorted, every key that
starts with a given prefix sits in one contiguous run. A **total proof** for a
prefix splits the tree into ``O(log n)`` pieces: subtrees entirely inside the run,
subtrees entirely outside it, and nothing else. The verifier rebuilds the root
from the pieces and checks, at every join it computes:

- the parent's sum and count are the children's sums and counts added up;
- the left child's largest key is no greater than the right child's smallest;
- the parent's hash commits to all of that.

It then checks that every inside piece's smallest and largest keys carry the
prefix, and that the pieces just outside the run don't. The total is the sum of
the inside pieces. Nothing in the proof is taken on trust except what the signed
root commits to.

What a proof can't show is that the signed tree was built honestly from the log:
that each record sits under the right key, with the right amount. Anyone can check
that by rebuilding the tree from the public log and comparing roots, the same way
the log itself is audited (ADR-0024).

Hashes use their own prefixes, 0x02 for leaves and 0x03 for nodes, so a sum-tree
hash can never be confused with a log hash (0x00 and 0x01).
"""

import bisect
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from tallyproof_core.hashing import EMPTY_ROOT, HASH_SIZE

SUM_LEAF_PREFIX = b"\x02"
SUM_NODE_PREFIX = b"\x03"
SEPARATOR = b"\x00"
"""Joins key components. It sorts below every other byte, so a prefix's run is contiguous."""

Key = tuple[str, ...]


class SumTreeError(ValueError):
    """Raised for malformed keys or leaves, and for proofs that can't be read."""


def encode_key(key: Sequence[str]) -> bytes:
    """The bytes a key is sorted and hashed by: its components joined by 0x00."""
    parts = [c.encode("utf-8") for c in key]
    if not parts or any(SEPARATOR in p for p in parts):
        raise SumTreeError(f"a key needs at least one component and no NUL characters: {key!r}")
    return SEPARATOR.join(parts)


def encode_prefix(prefix: Sequence[str]) -> bytes:
    """Bytes every key under ``prefix`` starts with (an empty prefix matches every key)."""
    return encode_key(prefix) + SEPARATOR if prefix else b""


def _lp(data: bytes) -> bytes:
    return len(data).to_bytes(4, "big") + data


def _int(value: int) -> bytes:
    return str(value).encode("ascii")


@dataclass(frozen=True)
class SumLeaf:
    """One record in the tree."""

    key: Key
    amount: int
    """Minor units (cents). Negative amounts, such as de-obligations, are allowed."""
    record_hash: bytes
    """The record's leaf hash in the Merkle log, which ties this leaf to a log proof."""

    def digest(self) -> bytes:
        """SHA-256(0x02 || key || amount || record hash), with lengths prefixed."""
        if len(self.record_hash) != HASH_SIZE:
            raise SumTreeError(f"record hashes are {HASH_SIZE} bytes")
        return hashlib.sha256(
            SUM_LEAF_PREFIX + _lp(encode_key(self.key)) + _lp(_int(self.amount)) + self.record_hash
        ).digest()


def node_digest(
    left: bytes, right: bytes, total: int, count: int, low: Sequence[str], high: Sequence[str]
) -> bytes:
    """SHA-256(0x03 || left || right || sum || count || smallest key || largest key)."""
    return _node_digest(left, right, total, count, encode_key(low), encode_key(high))


def _node_digest(
    left: bytes, right: bytes, total: int, count: int, low: bytes, high: bytes
) -> bytes:
    if len(left) != HASH_SIZE or len(right) != HASH_SIZE:
        raise SumTreeError(f"child hashes are {HASH_SIZE} bytes")
    return hashlib.sha256(
        SUM_NODE_PREFIX + left + right + _lp(_int(total)) + _lp(_int(count)) + _lp(low) + _lp(high)
    ).digest()


@dataclass(frozen=True)
class LeafPiece:
    """A single leaf, given in full; the verifier hashes it itself."""

    leaf: SumLeaf


@dataclass(frozen=True)
class NodePiece:
    """A subtree, given by its children's hashes and the values its own hash commits to."""

    left: bytes
    right: bytes
    total: int
    count: int
    low: Key
    high: Key


Piece = LeafPiece | NodePiece


@dataclass(frozen=True)
class TotalProof:
    """Everything needed to check the total of one key prefix against a signed root."""

    size: int
    """Leaves in the tree."""
    prefix: Key
    start: int
    """First leaf under the prefix."""
    end: int
    """One past the last leaf under the prefix; equal to ``start`` when none match."""
    pieces: tuple[Piece, ...]


@dataclass(frozen=True)
class Proven:
    """What a valid proof establishes."""

    total: int
    count: int


def _split(size: int) -> int:
    return 1 << ((size - 1).bit_length() - 1)


class SumTree:
    """A sum tree over a fixed set of leaves, with cached subtree values for fast proofs."""

    def __init__(self, leaves: Iterable[SumLeaf], cache_min: int = 256) -> None:
        """Sort the leaves by key and prepare the tree.

        Raises:
            SumTreeError: If two leaves share a key.
        """
        if cache_min < 1 or cache_min & (cache_min - 1):
            raise ValueError("cache_min must be a power of two")
        ordered = sorted(leaves, key=lambda leaf: encode_key(leaf.key))
        self._keys = [encode_key(leaf.key) for leaf in ordered]
        for a, b in zip(self._keys, self._keys[1:], strict=False):
            if a == b:
                raise SumTreeError(f"two leaves share the key {a!r}")
        self._leaves = ordered
        self._cache: dict[tuple[int, int], tuple[bytes, int]] = {}
        self._cache_min = cache_min

    @property
    def size(self) -> int:
        """Number of leaves."""
        return len(self._leaves)

    def _node(self, start: int, end: int) -> tuple[bytes, int]:
        """Hash and sum of the leaves ``[start, end)``."""
        count = end - start
        if count == 1:
            leaf = self._leaves[start]
            return leaf.digest(), leaf.amount
        complete = count & (count - 1) == 0
        if complete and count >= self._cache_min:
            cached = self._cache.get((start, count))
            if cached is not None:
                return cached
        k = _split(count)
        left, left_sum = self._node(start, start + k)
        right, right_sum = self._node(start + k, end)
        total = left_sum + right_sum
        digest = _node_digest(left, right, total, count, self._keys[start], self._keys[end - 1])
        if complete and count >= self._cache_min:
            self._cache[(start, count)] = (digest, total)
        return digest, total

    def root(self) -> bytes:
        """The root hash; the empty tree hashes to SHA-256 of the empty string."""
        return EMPTY_ROOT if not self._leaves else self._node(0, self.size)[0]

    def total(self) -> int:
        """The sum of every leaf."""
        return 0 if not self._leaves else self._node(0, self.size)[1]

    def run(self, prefix: Sequence[str]) -> tuple[int, int]:
        """The leaves ``[start, end)`` whose keys start with ``prefix``."""
        if not prefix:
            return 0, self.size
        low = encode_prefix(prefix)
        start = bisect.bisect_left(self._keys, low)
        end = bisect.bisect_left(self._keys, low[:-1] + b"\x01")  # just past the prefix's run
        return start, end

    def prove(self, prefix: Sequence[str]) -> TotalProof:
        """A proof of the total and count of every leaf under ``prefix``."""
        start, end = self.run(prefix)
        return self._prove(prefix, start, end)

    def _prove(self, prefix: Sequence[str], start: int, end: int) -> TotalProof:
        """A proof for an arbitrary run. Tests use it to forge proofs of the wrong run."""
        pieces: list[Piece] = []

        def walk(a: int, b: int) -> None:
            if b - a == 1:
                pieces.append(LeafPiece(self._leaves[a]))
                return
            if (start <= a and b <= end) or b <= start or a >= end:
                k = _split(b - a)
                left, _ = self._node(a, a + k)
                right, _ = self._node(a + k, b)
                _, total = self._node(a, b)
                pieces.append(
                    NodePiece(
                        left, right, total, b - a, self._leaves[a].key, self._leaves[b - 1].key
                    )
                )
                return
            k = _split(b - a)
            walk(a, a + k)
            walk(a + k, b)

        if self._leaves:
            walk(0, self.size)
        return TotalProof(self.size, tuple(prefix), start, end, tuple(pieces))


@dataclass
class _Built:
    digest: bytes
    total: int
    count: int
    low: bytes
    high: bytes


def verify_total(proof: TotalProof, root: bytes) -> Proven | None:
    """Check a total proof against a signed root. Returns None if anything fails.

    Never raises on bad input: a malformed proof is a failed proof.
    """
    try:
        return _verify(proof, root)
    except (SumTreeError, ValueError, IndexError, TypeError, AttributeError, StopIteration):
        return None


def _verify(proof: TotalProof, root: bytes) -> Proven | None:
    size, start, end = proof.size, proof.start, proof.end
    if size < 0 or not 0 <= start <= end <= size:
        return None
    if size == 0:
        return Proven(0, 0) if root == EMPTY_ROOT and not proof.pieces else None
    prefix = encode_prefix(proof.prefix)
    pieces = iter(proof.pieces)
    inside = Proven(0, 0)
    bounds: dict[int, _Built] = {}  # pieces keyed by where they start, for the edge checks

    def take(a: int, b: int) -> _Built:
        piece = next(pieces)
        if isinstance(piece, LeafPiece):
            if b - a != 1:
                raise SumTreeError("a leaf piece where a subtree belongs")
            key = encode_key(piece.leaf.key)
            built = _Built(piece.leaf.digest(), piece.leaf.amount, 1, key, key)
        else:
            if b - a < 2 or piece.count != b - a:
                raise SumTreeError("a subtree piece of the wrong size")
            low, high = encode_key(piece.low), encode_key(piece.high)
            if low > high:
                raise SumTreeError("a subtree whose smallest key is above its largest")
            digest = _node_digest(piece.left, piece.right, piece.total, piece.count, low, high)
            built = _Built(digest, piece.total, piece.count, low, high)
        return built

    def rebuild(a: int, b: int) -> _Built:
        nonlocal inside
        whole_inside = start <= a and b <= end
        whole_outside = b <= start or a >= end
        if b - a == 1 or whole_inside or whole_outside:
            built = take(a, b)
            if whole_inside and start < end:
                if not (built.low.startswith(prefix) and built.high.startswith(prefix)):
                    raise SumTreeError("an inside piece has a key outside the prefix")
                inside = Proven(inside.total + built.total, inside.count + built.count)
            bounds[a] = built
            return built
        k = _split(b - a)
        left = rebuild(a, a + k)
        right = rebuild(a + k, b)
        if left.high > right.low:
            raise SumTreeError("keys out of order")
        total, count = left.total + right.total, left.count + right.count
        digest = _node_digest(left.digest, right.digest, total, count, left.low, right.high)
        return _Built(digest, total, count, left.low, right.high)

    top = rebuild(0, size)
    if next(pieces, None) is not None:
        return None
    if top.digest != root:
        return None
    # The run is complete: the piece ending just before it, and the one starting just
    # after it, hold no key under the prefix.
    if prefix:
        before = next((p for a, p in bounds.items() if a < start and _ends_at(a, p, start)), None)
        if start > 0 and (before is None or before.high.startswith(prefix) or before.high > prefix):
            return None
        after = bounds.get(end)
        if end < size and (after is None or after.low.startswith(prefix) or after.low < prefix):
            return None
    return inside


def _ends_at(a: int, built: _Built, position: int) -> bool:
    return a + built.count == position


def proof_to_json(proof: TotalProof) -> dict[str, Any]:
    """A proof as JSON-ready values: hashes in hex, amounts as decimal strings of cents."""

    def piece(p: Piece) -> dict[str, Any]:
        if isinstance(p, LeafPiece):
            return {
                "leaf": {
                    "key": list(p.leaf.key),
                    "amount": str(p.leaf.amount),
                    "record_hash": p.leaf.record_hash.hex(),
                }
            }
        return {
            "node": {
                "left": p.left.hex(),
                "right": p.right.hex(),
                "total": str(p.total),
                "count": p.count,
                "low": list(p.low),
                "high": list(p.high),
            }
        }

    return {
        "size": proof.size,
        "prefix": list(proof.prefix),
        "start": proof.start,
        "end": proof.end,
        "pieces": [piece(p) for p in proof.pieces],
    }


def proof_from_json(data: dict[str, Any]) -> TotalProof:
    """Read a proof written by :func:`proof_to_json`.

    Raises:
        SumTreeError: If the data is malformed.
    """
    try:
        pieces: list[Piece] = []
        for p in data["pieces"]:
            if "leaf" in p:
                leaf = p["leaf"]
                pieces.append(
                    LeafPiece(
                        SumLeaf(
                            tuple(str(c) for c in leaf["key"]),
                            int(leaf["amount"]),
                            bytes.fromhex(leaf["record_hash"]),
                        )
                    )
                )
            else:
                node = p["node"]
                pieces.append(
                    NodePiece(
                        bytes.fromhex(node["left"]),
                        bytes.fromhex(node["right"]),
                        int(node["total"]),
                        int(node["count"]),
                        tuple(str(c) for c in node["low"]),
                        tuple(str(c) for c in node["high"]),
                    )
                )
        return TotalProof(
            int(data["size"]),
            tuple(str(c) for c in data["prefix"]),
            int(data["start"]),
            int(data["end"]),
            tuple(pieces),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SumTreeError(f"malformed total proof: {error}") from error
