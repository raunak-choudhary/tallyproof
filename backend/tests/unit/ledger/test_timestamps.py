import hashlib
from dataclasses import dataclass, field

import pytest
import requests

from apps.ledger.timestamps import HEADER_MAGIC, detached_file, stamp


@dataclass
class FakeResponse:
    content: bytes
    status: int = 200

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise requests.HTTPError(f"status {self.status}")


@dataclass
class FakeSession:
    answers: dict[str, FakeResponse | Exception]
    posted: list[tuple[str, bytes]] = field(default_factory=list)

    def post(self, url, data, headers, timeout):
        self.posted.append((url, data))
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_detached_file_layout():
    digest = hashlib.sha256(b"note").digest()
    data = detached_file(digest, b"\xf0\x10calendar-bytes")
    assert data.startswith(HEADER_MAGIC + b"\x01\x08" + digest)
    assert data.endswith(b"calendar-bytes")
    with pytest.raises(ValueError, match="32-byte"):
        detached_file(b"short", b"x")


def test_each_answering_calendar_gets_its_own_proof_and_failures_are_reported(tmp_path):
    session = FakeSession(
        {
            "https://a.example/digest": FakeResponse(b"\xf0\x01pending"),
            "https://b.example/digest": requests.ConnectionError("down"),
            "https://c.example/digest": FakeResponse(b"", status=503),
        }
    )
    target = tmp_path / "checkpoint-8.note"
    result = stamp(
        b"the note",
        target,
        ["https://a.example", "https://b.example", "https://c.example"],
        session=session,  # type: ignore[arg-type]
    )
    assert target.read_bytes() == b"the note"
    assert [p.name for p in result.written] == ["checkpoint-8.note.a.example.ots"]
    assert set(result.failed) == {"https://b.example", "https://c.example"}
    digest = hashlib.sha256(b"the note").digest()
    assert all(body == digest for _, body in session.posted)
    assert result.written[0].read_bytes() == detached_file(digest, b"\xf0\x01pending")
