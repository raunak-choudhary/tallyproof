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


def original(record: bytes) -> bytes:
    """The original message bytes kept inside a dead-letter record."""
    return base64.b64decode(json.loads(record)["raw_base64"])


def validate_fixed(lines: list[str]) -> list[tuple[int, list[dict[str, str]]]]:
    """Check fixed records before replay. Returns (line number, problems) for each bad one."""
    from tallyproof_core.events import EventEnvelope

    bad = []
    for number, line in enumerate(lines, start=1):
        try:
            EventEnvelope.model_validate_json(line)
        except (ValidationError, ValueError) as error:
            bad.append((number, describe(error)))
    return bad
