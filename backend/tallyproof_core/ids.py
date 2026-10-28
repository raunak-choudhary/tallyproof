"""Prefixed, sortable public IDs such as ``evt_01JBXQ4V6Z9GQ1W8R3T5Y7U2PA``.

Each ID is a type prefix and a ULID: a 48-bit millisecond timestamp followed by
80 random bits, written in Crockford base32. IDs sort by creation time, are safe
in URLs, and say what kind of object they name. Internal database keys never
appear in public URLs.

The clock and random source are passed in. Production uses the system clock and
a cryptographic random source; tests and reproducible scenarios pass a fixed
time and a seeded generator, so the same seed always yields the same IDs.
"""

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol

PREFIXES = frozenset({"evt", "bat", "src", "brk", "doc", "qry", "ans", "clm", "run"})
"""Every public ID prefix in use. See docs/backend-design.md."""

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
_ULID_LENGTH = 26
_TIMESTAMP_BITS = 48
_RANDOM_BITS = 80
_PATTERN = re.compile(rf"^([a-z]{{3}})_([{_ALPHABET}]{{{_ULID_LENGTH}}})$")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_MS = timedelta(milliseconds=1)


class RandomBits(Protocol):
    """Anything that can produce random integers, such as ``random.Random``."""

    def getrandbits(self, k: int, /) -> int:
        """Return a non-negative integer with ``k`` random bits."""
        ...


def _encode(value: int) -> str:
    chars = []
    for _ in range(_ULID_LENGTH):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_id(prefix: str, *, now: datetime | None = None, rng: RandomBits | None = None) -> str:
    """Create a new prefixed ID.

    Args:
        prefix: One of :data:`PREFIXES`, without the underscore.
        now: Creation time. Defaults to the current UTC time.
        rng: Random source. Defaults to a cryptographically secure generator.

    Returns:
        The ID, for example ``evt_01JBXQ4V6Z9GQ1W8R3T5Y7U2PA``.

    Raises:
        ValueError: If the prefix is unknown or the time is not timezone aware.
    """
    if prefix not in PREFIXES:
        raise ValueError(f"unknown ID prefix {prefix!r}")
    now = now or datetime.now(tz=UTC)
    if now.tzinfo is None:
        raise ValueError("ID timestamps must be timezone aware")
    # Integer arithmetic on timedeltas: going through a float timestamp can drop a millisecond.
    millis = (now - _EPOCH) // _ONE_MS
    if not 0 <= millis < 1 << _TIMESTAMP_BITS:
        raise ValueError("timestamp is outside the range a ULID can hold")
    randomness = (rng or secrets.SystemRandom()).getrandbits(_RANDOM_BITS)
    return f"{prefix}_{_encode(millis << _RANDOM_BITS | randomness)}"


def parse_id(value: str, *, expected_prefix: str | None = None) -> tuple[str, datetime]:
    """Validate an ID and return its prefix and creation time.

    Args:
        value: The ID to check.
        expected_prefix: If given, the ID must have this prefix.

    Returns:
        The prefix and the UTC timestamp encoded in the ID.

    Raises:
        ValueError: If the ID is malformed or has the wrong prefix.
    """
    match = _PATTERN.match(value)
    if not match or match.group(1) not in PREFIXES:
        raise ValueError(f"not a valid ID: {value!r}")
    prefix, body = match.groups()
    if expected_prefix is not None and prefix != expected_prefix:
        raise ValueError(f"expected a {expected_prefix}_ ID, got {value!r}")
    number = 0
    for char in body:
        number = number << 5 | _ALPHABET.index(char)
    if number >> 128:
        raise ValueError(f"not a valid ID: {value!r}")
    try:
        created = _EPOCH + (number >> _RANDOM_BITS) * _ONE_MS
    except OverflowError as error:
        # ULIDs can encode times past the year 9999, which datetime cannot represent.
        raise ValueError(f"not a valid ID: {value!r}") from error
    return prefix, created
