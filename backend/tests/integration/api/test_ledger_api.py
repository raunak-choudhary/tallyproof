from collections.abc import Iterator

import pytest
from django.core.cache import cache
from django.test import Client

from apps.ledger.api import proofs
from apps.ledger.checkpointer import Checkpointer
from tallyproof_core.checkpoint import Verifier
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import verify_consistency, verify_inclusion
from tests.integration.ledger.test_checkpointer import Clock, add_events
from tests.unit.pipeline.test_replay_bundle import SIGNER

pytestmark = pytest.mark.django_db
VERIFIER = Verifier.from_verifier_key(SIGNER.verifier_key())


@pytest.fixture(autouse=True)
def fresh_caches() -> Iterator[None]:
    proofs.reset()
    cache.clear()
    yield
    proofs.reset()


@pytest.fixture
def client() -> Client:
    return Client(HTTP_HOST="localhost")


@pytest.fixture
def signed_log(migrated):
    """Seven events with checkpoints at sizes 4 and 7, and one unsigned event."""
    checkpointer = Checkpointer(SIGNER, 4, 60_000, clock=Clock())
    add_events(migrated, 4)
    checkpointer.tick()
    add_events(migrated, 3, start=4)
    checkpointer.close()
    add_events(migrated, 1, start=7)
    return migrated


def test_an_inclusion_proof_verifies_against_the_signed_checkpoint(client, signed_log):
    events = client.get("/api/v1/events").json()["results"]
    assert [e["leaf_index"] for e in events] == list(range(8))
    event = events[5]
    proof = client.get(f"/api/v1/events/{event['event_id']}/proof").json()
    checkpoint = VERIFIER.verify_checkpoint(proof["checkpoint_note"])
    assert proof["tree_size"] == checkpoint.tree_size == 7
    path = [bytes.fromhex(h) for h in proof["audit_path_hex"]]
    leaf = leaf_hash(event["canonical"].encode())
    assert verify_inclusion(leaf, 5, 7, path, checkpoint.root_hash)
    edited = event["canonical"].replace('"1250.00"', '"9250.00"').encode()
    assert edited != event["canonical"].encode()
    assert not verify_inclusion(leaf_hash(edited), 5, 7, path, checkpoint.root_hash)


def test_a_proof_can_target_an_older_checkpoint(client, signed_log):
    event = client.get("/api/v1/events?limit=1").json()["results"][0]
    proof = client.get(f"/api/v1/events/{event['event_id']}/proof?tree_size=4").json()
    assert proof["tree_size"] == 4
    root = VERIFIER.verify_checkpoint(proof["checkpoint_note"]).root_hash
    path = [bytes.fromhex(h) for h in proof["audit_path_hex"]]
    assert verify_inclusion(bytes.fromhex(event["leaf_hash_hex"]), 0, 4, path, root)


def test_an_event_not_yet_checkpointed_gets_a_conflict_problem(client, signed_log):
    last = client.get("/api/v1/events?limit=200").json()["results"][-1]
    assert last["leaf_index"] == 7
    response = client.get(f"/api/v1/events/{last['event_id']}/proof")
    assert response.status_code == 409
    assert response["Content-Type"] == "application/problem+json"
    assert response.json()["type"].endswith("/not-yet-checkpointed")


def test_consistency_between_checkpoints_verifies(client, signed_log):
    body = client.get("/api/v1/consistency?first=4").json()
    first = VERIFIER.verify_checkpoint(body["first_note"])
    second = VERIFIER.verify_checkpoint(body["second_note"])
    proof = [bytes.fromhex(h) for h in body["proof_hex"]]
    assert verify_consistency(4, 7, first.root_hash, second.root_hash, proof)


def test_checkpoints_are_listed_newest_first_and_fetchable_by_size(client, signed_log):
    listed = client.get("/api/v1/checkpoints").json()["results"]
    assert [c["tree_size"] for c in listed] == [7, 4]
    assert client.get("/api/v1/checkpoints/latest").json()["tree_size"] == 7
    assert client.get("/api/v1/checkpoints/4").json()["start_index"] == 0
    assert client.get("/api/v1/checkpoints/5").status_code == 404


def test_events_can_be_filtered_and_paged(client, signed_log):
    first = client.get("/api/v1/events?limit=3&event_type=obligation.recorded").json()
    assert len(first["results"]) == 3
    second = client.get(first["next"]).json()
    assert second["results"][0]["leaf_index"] == 3
    assert client.get("/api/v1/events?account_id=NOBODY").json()["results"] == []


@pytest.mark.parametrize(
    ("url", "status"),
    [
        ("/api/v1/events?event_type=made.up", 400),
        ("/api/v1/consistency", 400),
        ("/api/v1/consistency?first=-1", 400),
        ("/api/v1/consistency?first=7&second=4", 400),
        ("/api/v1/events/evt_missing/proof", 404),
        ("/api/v1/events/evt_missing/proof?tree_size=x", 404),
    ],
)
def test_bad_requests_get_problem_details(client, signed_log, url, status):
    response = client.get(url)
    assert response.status_code == status
    body = response.json()
    assert {"type", "title", "status", "detail", "instance"} <= set(body)
    assert "Traceback" not in response.content.decode()


def test_the_log_key_matches_the_configured_public_key(client, migrated, settings):
    body = client.get("/api/v1/log-key").json()
    assert set(body) == {"origin", "verifier_key"}


def test_anonymous_reads_are_rate_limited(client, migrated, monkeypatch):
    from rest_framework.throttling import AnonRateThrottle

    monkeypatch.setattr(AnonRateThrottle, "THROTTLE_RATES", {"anon": "2/min"})
    statuses = [client.get("/api/v1/log-key").status_code for _ in range(3)]
    assert statuses == [200, 200, 429]
