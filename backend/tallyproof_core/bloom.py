"""A Bloom filter for the ingestion deduplication fast path.

A Bloom filter answers "have I seen this key?" with either "definitely not" or
"maybe". It never gives a false negative, which is the property ingestion relies
on: keys reported as definitely new can skip duplicate handling. A "maybe" can
be wrong, so the database's unique constraint stays the authority (ADR-0008).

Positions are derived by double hashing: two 64-bit values from one SHA-256
digest generate all k positions as ``h1 + i * h2`` (Kirsch and Mitzenmacher,
2006), which keeps the false-positive rate of k independent hashes at the cost
of one.
"""

import hashlib
import math
import struct

_HEADER = struct.Struct(">4sQII")  # magic, bit count, hash count, item count
_MAGIC = b"TPBF"
_MAX_BITS = 2**34  # 2 GiB of bits; far above anything ingestion needs


class BloomFilter:
    """A fixed-size Bloom filter over byte strings."""

    def __init__(self, num_bits: int, num_hashes: int) -> None:
        """Create an empty filter.

        Args:
            num_bits: Size of the bit array.
            num_hashes: Number of positions set per key.

        Raises:
            ValueError: If either value is out of range.
        """
        if not 8 <= num_bits <= _MAX_BITS:
            raise ValueError(f"num_bits must be between 8 and {_MAX_BITS}")
        if not 1 <= num_hashes <= 64:
            raise ValueError("num_hashes must be between 1 and 64")
        self.num_bits = num_bits
        self.num_hashes = num_hashes
        self.count = 0
        self._bits = bytearray((num_bits + 7) // 8)

    @classmethod
    def for_capacity(cls, expected_items: int, false_positive_rate: float) -> "BloomFilter":
        """Size a filter for a number of keys and a target false-positive rate.

        Uses the standard optimum: m = -n ln(p) / (ln 2)^2 bits and
        k = (m / n) ln 2 hash functions.

        Args:
            expected_items: How many keys the filter should hold, n.
            false_positive_rate: Target probability of a wrong "maybe", p.

        Returns:
            An empty filter sized for that load.

        Raises:
            ValueError: If the arguments are out of range.
        """
        if expected_items < 1:
            raise ValueError("expected_items must be at least 1")
        if not 0 < false_positive_rate < 1:
            raise ValueError("false_positive_rate must be between 0 and 1")
        bits = math.ceil(-expected_items * math.log(false_positive_rate) / math.log(2) ** 2)
        hashes = max(1, round(bits / expected_items * math.log(2)))
        return cls(max(bits, 8), hashes)

    def _positions(self, key: bytes) -> list[int]:
        digest = hashlib.sha256(key).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:16], "big") | 1  # odd, so it never collapses to h1
        return [(h1 + i * h2) % self.num_bits for i in range(self.num_hashes)]

    def add(self, key: bytes) -> None:
        """Record a key."""
        for position in self._positions(key):
            self._bits[position >> 3] |= 1 << (position & 7)
        self.count += 1

    def might_contain(self, key: bytes) -> bool:
        """Return False if the key was definitely never added, True if it may have been."""
        return all(
            self._bits[position >> 3] & (1 << (position & 7)) for position in self._positions(key)
        )

    def __contains__(self, key: bytes) -> bool:
        """Support ``key in bloom``; same meaning as :meth:`might_contain`."""
        return self.might_contain(key)

    @property
    def expected_false_positive_rate(self) -> float:
        """Estimated false-positive rate for the keys added so far: (1 - e^(-kn/m))^k."""
        return (1 - math.exp(-self.num_hashes * self.count / self.num_bits)) ** self.num_hashes

    def to_bytes(self) -> bytes:
        """Serialize the filter, for example to snapshot it alongside a consumer offset."""
        return _HEADER.pack(_MAGIC, self.num_bits, self.num_hashes, self.count) + bytes(self._bits)

    @classmethod
    def from_bytes(cls, data: bytes) -> "BloomFilter":
        """Restore a filter written by :meth:`to_bytes`.

        Raises:
            ValueError: If the data is not a serialized filter.
        """
        if len(data) < _HEADER.size:
            raise ValueError("not a serialized Bloom filter")
        magic, num_bits, num_hashes, count = _HEADER.unpack_from(data)
        if magic != _MAGIC:
            raise ValueError("not a serialized Bloom filter")
        bloom = cls(num_bits, num_hashes)
        body = data[_HEADER.size :]
        if len(body) != len(bloom._bits):
            raise ValueError("serialized Bloom filter has the wrong length")
        bloom._bits[:] = body
        bloom.count = count
        return bloom
