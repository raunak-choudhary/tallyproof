"""Records that failed validation, wrapped with why and where they came from."""

import base64
import json
from datetime import UTC, datetime

from pydantic import ValidationError

MAX_RAW_BYTES = 65_536
"""Longest original value kept in a dead-letter record."""


def describe(error: Exception) -> list[dict[str, str]]:
    """Summarize a parse or validation error without echoing the offending values."""
    if isinstance(error, ValidationError):
        # Pydantic's own messages never include the input, but messages raised by
        # our validators can (for example the money parser), so those are reduced
        # to their error type. The original record is kept separately, encoded.
        return [
            {
                "field": ".".join(str(p) for p in e["loc"]) or "(record)",
                "problem": e["type"] if e["type"] == "value_error" else e["msg"],
            }
            for e in error.errors(include_input=False, include_url=False)
        ]
    return [{"field": "(record)", "problem": type(error).__name__}]


def envelope(error: Exception, topic: str, partition: int, offset: int, raw: bytes | None) -> bytes:
    """Build the dead-letter record for one rejected message."""
    body = raw or b""
    record = {
        "error": "schema_invalid",
        "problems": describe(error),
        "source": {"topic": topic, "partition": partition, "offset": offset},
        "rejected_at": datetime.now(UTC).isoformat(),
        "raw_base64": base64.b64encode(body[:MAX_RAW_BYTES]).decode(),
        "raw_truncated": len(body) > MAX_RAW_BYTES,
    }
    return json.dumps(record, sort_keys=True).encode()
