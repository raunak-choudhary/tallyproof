"""A Count-Min Sketch: approximate counts per key in fixed memory.

The sketch is ``depth`` rows of ``width`` counters. Adding a key increments one
counter in each row; its estimate is the smallest of those counters. Collisions
only ever add, so an estimate is never below the true count. With ``N`` additions
in total, it is above the true count by more than ``epsilon * N`` with probability
at most ``delta``, where ``epsilon = e / width`` and ``delta = e ** -depth``
(Cormode and Muthukrishnan, 2005).

Counters are indexed by BLAKE2b digests of the key, not Python's ``hash``, which is
salted per process: the same keys always land in the same counters, so the rules
built on the sketch give the same answers on every run.
"""

import hashlib
import math
from array import array


class CountMinSketch:
    """Approximate counts that never undercount, in ``width * depth`` counters."""

    def __init__(self, width: int, depth: int) -> None:
        """Create an empty sketch.

        Args:
            width: Counters per row; the error bound shrinks as it grows.
            depth: Rows; the chance of exceeding the bound shrinks as it grows.
        """
        if width < 1 or not 1 <= depth <= 8:
            raise ValueError("width must be positive and depth between 1 and 8")
        self.width = width
        self.depth = depth
        self.total = 0
        self._rows = [array("I", [0]) * width for _ in range(depth)]

    @classmethod
    def for_error(cls, epsilon: float, delta: float) -> "CountMinSketch":
        """The smallest sketch that overcounts by under ``epsilon * N``, except w.p. ``delta``."""
        if not 0 < epsilon < 1 or not 0 < delta < 1:
            raise ValueError("epsilon and delta must be between 0 and 1")
        return cls(math.ceil(math.e / epsilon), math.ceil(math.log(1 / delta)))

    @property
    def epsilon(self) -> float:
        """Relative error bound: overcounts stay below ``epsilon * total`` ..."""
        return math.e / self.width

    @property
    def delta(self) -> float:
        """... except with this probability."""
        return math.exp(-self.depth)

    def _slots(self, key: bytes) -> list[int]:
        digest = hashlib.blake2b(key, digest_size=8 * self.depth).digest()
        return [
            int.from_bytes(digest[8 * i : 8 * i + 8], "big") % self.width for i in range(self.depth)
        ]

    def add(self, key: bytes, count: int = 1) -> int:
        """Add ``count`` to a key and return its new estimate."""
        if count < 0:
            raise ValueError("a Count-Min Sketch only counts up")
        self.total += count
        estimate = None
        for row, slot in zip(self._rows, self._slots(key), strict=True):
            row[slot] += count
            estimate = row[slot] if estimate is None else min(estimate, row[slot])
        return int(estimate or 0)

    def estimate(self, key: bytes) -> int:
        """At least the true count; above it by more than ``epsilon * total`` w.p. at most delta."""
        return min(row[slot] for row, slot in zip(self._rows, self._slots(key), strict=True))
