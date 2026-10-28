"""External timestamps for checkpoints, using public OpenTimestamps calendars.

A calendar server takes a SHA-256 digest and returns a pending timestamp that it
later anchors in the Bitcoin blockchain. Anyone can then prove the checkpoint
existed by that time with the standard ``ots`` tool, without trusting us or the
calendar. That is what bounds a key thief to the witness interval (tamper ladder
level 3 in docs/architecture.md).

This module only submits digests and writes the standard detached proof file
(``.ots``), one per calendar. Upgrading and verifying proofs is left to the
official client; name the stamped file explicitly, since each proof file carries
its calendar's host name::

    ots upgrade checkpoint-1024.note.a.pool.opentimestamps.org.ots
    ots verify -f checkpoint-1024.note checkpoint-1024.note.a.pool.opentimestamps.org.ots
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

HEADER_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
"""Opening bytes of every detached timestamp file."""
FORMAT_VERSION = b"\x01"
OP_SHA256 = b"\x08"
MAX_RESPONSE_BYTES = 10_000


@dataclass(frozen=True)
class StampResult:
    """Which calendars accepted the digest, and where their proofs were written."""

    written: list[Path]
    failed: dict[str, str]


def detached_file(digest: bytes, calendar_timestamp: bytes) -> bytes:
    """Wrap a calendar's answer in the detached ``.ots`` file format for a SHA-256 digest."""
    if len(digest) != 32:
        raise ValueError("digest must be a 32-byte SHA-256")
    return HEADER_MAGIC + FORMAT_VERSION + OP_SHA256 + digest + calendar_timestamp


def stamp(
    data: bytes,
    target: Path,
    calendars: Sequence[str],
    session: requests.Session | None = None,
    timeout: float = 10.0,
) -> StampResult:
    """Write ``data`` to ``target`` and ask each calendar to timestamp its SHA-256.

    One proof file is written per calendar that answers, named
    ``<target>.<calendar host>.ots``, so each is a complete proof on its own.
    Failures are returned, not raised: a calendar being down must not stop the
    ledger, and the next witness interval tries again.
    """
    http = session or requests.Session()
    digest = hashlib.sha256(data).digest()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    written: list[Path] = []
    failed: dict[str, str] = {}
    for calendar in calendars:
        host = urlparse(calendar).hostname or "calendar"
        try:
            response = http.post(
                f"{calendar}/digest",
                data=digest,
                headers={"Accept": "application/vnd.opentimestamps.v1"},
                timeout=timeout,
            )
            response.raise_for_status()
            body = response.content
            if not body or len(body) > MAX_RESPONSE_BYTES:
                raise ValueError(f"unexpected response size {len(body)}")
        except (requests.RequestException, ValueError) as error:
            failed[calendar] = str(error)
            continue
        proof = target.with_name(f"{target.name}.{host}.ots")
        proof.write_bytes(detached_file(digest, body))
        written.append(proof)
    return StampResult(written, failed)
