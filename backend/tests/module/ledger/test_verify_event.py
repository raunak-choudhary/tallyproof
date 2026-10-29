"""The ledger's terminal check, run against a fake API that serves a real signed log.

``verify_event`` trusts only the pinned key. These tests serve it honest answers and
four kinds of wrong ones, and expect it to pass only the honest one.
"""

from types import SimpleNamespace
from typing import Any

import pytest
import requests
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ledger.management.commands import verify_event
from tallyproof_core.canonical import canonicalize
from tallyproof_core.checkpoint import Checkpoint
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import inclusion_proof, root
from tests.unit.pipeline.test_replay_bundle import SIGNER

API = "http://127.0.0.1:8000"
RECORDS = [
    canonicalize({"event_id": f"evt_{n}", "payload": {"amount": f"{n}.00"}}).decode()
    for n in range(6)
]
LEAVES = [leaf_hash(r.encode()) for r in RECORDS]
NOTE = SIGNER.sign_checkpoint(Checkpoint(SIGNER.name, len(LEAVES), root(LEAVES)))


class Reply:
    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body

    def json(self) -> dict[str, Any]:
        return self.body


class FakeApi:
    """Serves events and proofs the way the ledger API does, with optional lies."""

    def __init__(self, **lies: Any) -> None:
        self.lies = lies

    def __enter__(self) -> "FakeApi":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, url: str, timeout: float) -> Reply:
        event_id = url.split("/events/")[1].split("/")[0]
        index = int(event_id.removeprefix("evt_"))
        if url.endswith("/proof"):
            served = self.lies.get("proof_for", index)
            return Reply(
                {
                    "leaf_index": self.lies.get("leaf_index", served),
                    "tree_size": len(LEAVES),
                    "audit_path_hex": [h.hex() for h in inclusion_proof(LEAVES, served)],
                    "checkpoint_note": self.lies.get("note", NOTE),
                }
            )
        record = self.lies.get("record", RECORDS[self.lies.get("record_for", index)])
        return Reply({"event_id": event_id, "canonical": record})


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(api_base_url=API, checkpoint_public_key=SIGNER.verifier_key())
    monkeypatch.setattr(verify_event, "app_settings", lambda: settings)


def run(api: FakeApi, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> str:
    monkeypatch.setattr(requests, "Session", lambda: api)
    call_command("verify_event", "--event", "evt_3")
    return capsys.readouterr().out


def test_an_honest_answer_verifies(pinned, monkeypatch, capsys):
    out = run(FakeApi(), monkeypatch, capsys)
    assert "checkpoint signature: ok" in out
    assert "evt_3 verified" in out


@pytest.mark.parametrize(
    ("lies", "message"),
    [
        ({"record": RECORDS[3].replace("3.00", "9.00")}, "inclusion proof: FAILED"),
        ({"note": NOTE.replace("6\n", "7\n", 1)}, "checkpoint signature: FAILED"),
        # A valid record and proof, but for another event than the one asked about.
        ({"record_for": 4, "proof_for": 4}, "is for evt_4"),
        ({"leaf_index": 4, "proof_for": 4, "record_for": 4}, "is for evt_4"),
    ],
)
def test_a_wrong_answer_fails(pinned, monkeypatch, capsys, lies, message):
    with pytest.raises(CommandError, match=message):
        run(FakeApi(**lies), monkeypatch, capsys)
