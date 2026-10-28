"""Framework-free core of Tallyproof.

This package holds the code a careful reader will scrutinize most: canonical
serialization, hashing, the Merkle log, signed checkpoints, and the Bloom filter.
It has no Django imports and does no I/O, so it can be tested in isolation and
mirrored exactly by the browser verification library.
"""

__all__: list[str] = []
