"""Canonical JSON bytes for hashing and signing (RFC 8785).

A leaf hash is only meaningful if the browser can reproduce the exact same
bytes. RFC 8785 fixes key order, whitespace, and string escaping. On top of
that, this module rejects the values that most often break agreement between
languages:

- Non-integer numbers. JavaScript and Python format floats differently, so
  money, rates, and quantities must be decimal strings.
- Integers outside 0 to 2**53 - 1, which JavaScript cannot represent exactly.
- Strings that are not valid Unicode, such as lone surrogates, which Python
  refuses to encode and JavaScript silently escapes.
"""

from collections.abc import Mapping, Sequence

import rfc8785

MAX_SAFE_INTEGER = 2**53 - 1
"""Largest integer every JSON implementation in the project represents exactly."""


class CanonicalizationError(ValueError):
    """Raised when a value cannot be canonicalized safely across languages."""


def _check(value: object, path: str) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not 0 <= value <= MAX_SAFE_INTEGER:
            raise CanonicalizationError(f"{path}: integer {value} is outside 0..2**53-1")
        return
    if isinstance(value, float):
        raise CanonicalizationError(f"{path}: floats are not allowed; use a decimal string")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise CanonicalizationError(f"{path}: string is not valid Unicode") from error
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"{path}: object keys must be strings")
            _check(key, f"{path}.<key>")
            _check(item, f"{path}.{key}")
        return
    if isinstance(value, Sequence):
        for index, item in enumerate(value):
            _check(item, f"{path}[{index}]")
        return
    raise CanonicalizationError(f"{path}: unsupported type {type(value).__name__}")


def canonicalize(value: object) -> bytes:
    """Serialize a JSON-compatible value to RFC 8785 canonical bytes.

    Args:
        value: Nested dicts, lists, strings, non-negative safe integers,
            booleans, and None.

    Returns:
        The canonical UTF-8 bytes.

    Raises:
        CanonicalizationError: If the value contains anything that could
            serialize differently in another language.
    """
    _check(value, "$")
    # _check has validated every node, so the value matches what rfc8785 accepts.
    return rfc8785.dumps(value)  # type: ignore[arg-type]
