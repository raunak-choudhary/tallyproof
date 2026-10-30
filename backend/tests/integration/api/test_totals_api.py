"""The totals API: signed sum roots, and proofs a client checks without the records."""

from collections.abc import Iterator

import pytest
from django.core.cache import cache
from django.test import Client

from apps.ledger.api import proofs
from apps.ledger.totals import TotalsSigner
from tallyproof_core.checkpoint import Verifier
from tallyproof_core.sum_tree import proof_from_json, verify_total
from tests.fakes import FrozenClock
from tests.integration.conftest import Database
from tests.integration.ledger.test_checkpointer import add_events
from tests.unit.pipeline.test_replay_bundle import SIGNER

pytestmark = pytest.mark.django_db
VERIFIER = Verifier.from_verifier_key(SIGNER.verifier_key())
ENERGY = "Department of Energy"


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
def signed_totals(migrated: Database) -> Database:
    """Six obligations of 1,250.00 for Energy, with totals signed at 4 and 6."""
    signer = TotalsSigner(SIGNER, 50_000, 300, clock=FrozenClock())
    add_events(migrated, 4)
    signer.sign(4)
    add_events(migrated, 2, start=4)
    signer.sign(6)
    return migrated


def test_the_latest_totals_are_signed(client: Client, signed_totals: Database) -> None:
    body = client.get("/api/v1/totals/latest").json()
    note = VERIFIER.verify_totals(body["totals_note"])
    assert (body["tree_size"], body["records"]) == (6, 6)
    assert note.root_hash.hex() == body["root_hash_hex"]


def test_a_proof_checks_against_the_signed_root_without_the_records(
    client: Client, signed_totals: Database
) -> None:
    body = client.get("/api/v1/totals/proof", {"entity": "obligations", "agency": ENERGY}).json()
    root = VERIFIER.verify_totals(body["totals_note"]).root_hash
    proven = verify_total(proof_from_json(body["proof"]), root)
    assert proven is not None
    assert (proven.total, proven.count) == (750_000, 6)
    assert (body["total_cents"], body["count"]) == ("750000", 6)


def test_an_older_checkpoint_can_be_proven(client: Client, signed_totals: Database) -> None:
    params: dict[str, str | int] = {
        "entity": "obligations",
        "agency": ENERGY,
        "fiscal_year": 2025,
        "tree_size": 4,
    }
    body = client.get("/api/v1/totals/proof", params).json()
    assert (body["tree_size"], body["total_cents"], body["count"]) == (4, "500000", 4)


def test_an_agency_with_no_records_proves_zero(client: Client, signed_totals: Database) -> None:
    body = client.get("/api/v1/totals/proof", {"entity": "outlays", "agency": ENERGY}).json()
    assert (body["total_cents"], body["count"]) == ("0", 0)


@pytest.mark.parametrize(
    "params",
    [
        {"entity": "awards"},
        {"entity": "obligations", "fiscal_year": 2025},
        {"entity": "obligations", "fiscal_year": "twenty"},
        {"entity": "obligations", "agency": "x" * 201},
    ],
)
def test_questions_it_cannot_prove_are_refused(
    client: Client, signed_totals: Database, params: dict[str, str | int]
) -> None:
    assert client.get("/api/v1/totals/proof", params).status_code == 400


def test_totals_that_were_never_signed_are_not_found(client: Client, migrated: Database) -> None:
    assert client.get("/api/v1/totals/latest").status_code == 404
    assert client.get("/api/v1/totals/proof", {"entity": "obligations"}).status_code == 404
