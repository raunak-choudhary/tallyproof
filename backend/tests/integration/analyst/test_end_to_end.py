"""From generated events to an answer whose every citation verifies.

The evaluation dataset (real awards with labeled anomalies mixed in) goes through
real Redpanda and the real ingestion consumer, then the projections and the
checkpointer. Questions go through the API. The model's replies are replayed
from recordings in ``testdata/llm_recordings/e2e``; with ``E2E_RECORD=1`` the
scripted replies below are recorded instead. Every cited event is then fetched
from the proof API and checked the way the browser checks it.
"""

import json
import os
import time
from decimal import Decimal
from functools import partial
from typing import Any

import pytest
from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from django.core.cache import cache
from django.test import Client
from testcontainers.community.kafka import RedpandaContainer

from apps.analyst import api
from apps.analyst.llm import CachingClient, FakeClient, LLMRequest
from apps.analyst.pipeline import Models
from apps.analyst.service import answer_question
from apps.ingestion.consumer import Ingestor, run
from apps.ingestion.dedupe import PartitionFilters
from apps.ledger.api import proofs
from apps.ledger.checkpointer import Checkpointer
from apps.ledger.projections import catch_up
from apps.ledger.totals import TotalsSigner
from apps.reconciliation.projection import ReconciliationProjection
from evals.dataset import OUT_DIR
from evals.oracle import Oracle
from tallyproof_core.checkpoint import Verifier
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import verify_inclusion
from tallyproof_core.sum_tree import proof_from_json, verify_total
from tallyproof_pipeline.gold import read_events
from tallyproof_pipeline.settings import REPO_ROOT
from tallyproof_pipeline.stream import interleave, publish
from tests.integration.analyst.conftest import AsAnalyst
from tests.unit.pipeline.test_replay_bundle import SIGNER

pytestmark = pytest.mark.django_db
RAW, DLQ, GROUP = "e2e.events.raw.v1", "e2e.events.dlq.v1", "ingest-analyst-e2e"
IPV4 = {"broker.address.family": "v4"}
RECORDINGS = REPO_ROOT / "testdata" / "llm_recordings" / "e2e"
INGEST_DEADLINE_SECONDS = 240
HHS = "Department of Health and Human Services"
MODELS = Models("recorded-router", "recorded-answer", 1200, 1000, "low")
"""Pinned, so the recordings never depend on whoever runs the test or their .env."""


def script(request: LLMRequest) -> str:
    """What the model is recorded saying."""
    if request.prompt_version == "router.v2":
        spec = {
            "shape": "aggregate",
            "entity": "obligations",
            "metric": "sum_amount",
            "filters": [{"field": "awarding_agency", "op": "eq", "value": HHS}],
        }
        return json.dumps({"category": "numeric_aggregate", "spec": spec})
    if "outlay with no recorded award" in request.messages[1].content:
        return json.dumps(
            {"answer": "Payments were made on awards that were never recorded: {{s1}} [[c1]], "
                       "{{s3}} [[c2]], and {{s5}} [[c3]]."}
        )  # fmt: skip
    return json.dumps({"answer": "HHS obligated {{s1}} across {{s2}} contract actions [[c1]]."})


def client_for_test() -> Any:
    if os.environ.get("E2E_RECORD") == "1":
        return CachingClient(RECORDINGS, FakeClient(script))
    return CachingClient(RECORDINGS)


def ingest(redpanda: RedpandaContainer) -> int:
    servers = redpanda.get_bootstrap_server()
    admin = AdminClient({"bootstrap.servers": servers, **IPV4})
    for future in admin.create_topics([NewTopic(RAW, 3, 1), NewTopic(DLQ, 1, 1)]).values():
        future.result(timeout=30)
    events = list(read_events(OUT_DIR / "events.jsonl.gz"))
    producer = Producer({"bootstrap.servers": servers, "acks": "all", **IPV4})
    publish(list(interleave(events, [])), producer, RAW, rate_per_sec=5000)
    ingestor = Ingestor(
        GROUP,
        DLQ,
        Producer({"bootstrap.servers": servers, **IPV4}),
        PartitionFilters(10_000, 0.001),
    )
    consumer = Consumer(
        {
            "bootstrap.servers": servers,
            "group.id": GROUP,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            **IPV4,
        }
    )
    # Generous for a slow CI machine; the assertion below says so if it isn't enough.
    deadline = time.monotonic() + INGEST_DEADLINE_SECONDS
    totals = ingestor.totals
    run(
        ingestor,
        consumer,
        RAW,
        max_batch=200,
        should_stop=lambda: (
            totals.appended + totals.duplicates >= len(events) or time.monotonic() > deadline
        ),
    )
    # A partial ingest would still answer some questions, then miss the recordings for
    # others and be refused, which hides the real cause. Fail here instead.
    processed = totals.appended + totals.duplicates
    assert processed == len(events), (
        f"ingested {processed} of {len(events)} events in {INGEST_DEADLINE_SECONDS} s"
    )
    return totals.appended


def verify_citations(client: Client, body: dict[str, Any]) -> int:
    verifier = Verifier.from_verifier_key(SIGNER.verifier_key())
    checked = 0
    for citation in body["citations"]:
        for cited in citation["events"]:
            event = client.get(f"/api/v1/events/{cited['event_id']}").json()
            proof = client.get(cited["proof_url"]).json()
            checkpoint = verifier.verify_checkpoint(proof["checkpoint_note"])
            assert checkpoint.tree_size == body["checkpoint_tree_size"]
            path = [bytes.fromhex(h) for h in proof["audit_path_hex"]]
            leaf = leaf_hash(event["canonical"].encode())
            assert verify_inclusion(
                leaf, cited["leaf_index"], checkpoint.tree_size, path, checkpoint.root_hash
            )
            checked += 1
    return checked


def test_questions_get_answers_whose_every_citation_verifies(
    redpanda, migrated, as_analyst, monkeypatch
):
    appended = ingest(redpanda)
    catch_up(ReconciliationProjection())
    Checkpointer(SIGNER, 10_000, 2000).close()
    TotalsSigner(SIGNER, 50_000, 300).sign(appended)
    proofs.reset()
    cache.clear()
    monkeypatch.setattr(
        api,
        "answer_question",
        partial(
            answer_question,
            executor=AsAnalyst(),
            client=client_for_test(),
            search=lambda q, k: [],
            chosen=MODELS,
        ),
    )
    client = Client(HTTP_HOST="localhost")
    oracle = Oracle()

    body = client.post(
        "/api/v1/queries", {"question": "How much did HHS obligate?"}, "application/json"
    ).json()
    assert body["status"] == "answered", body
    expected = oracle.expected({"kind": "sum", "entity": "obligations", "awarding_agency": HHS})
    assert body["slots"][0]["value"] == str(expected.amount)
    assert {e["event_id"] for c in body["citations"] for e in c["events"]} == expected.must_cite
    assert verify_citations(client, body) == len(expected.must_cite)
    # The same total, proven as a whole against the signed sum tree, without its records.
    (cited,) = body["citations"]
    proof_body = client.get(cited["total_proof_url"]).json()
    note = Verifier.from_verifier_key(SIGNER.verifier_key()).verify_totals(
        proof_body["totals_note"]
    )
    assert note.tree_size == body["checkpoint_tree_size"]
    proven = verify_total(proof_from_json(proof_body["proof"]), note.root_hash)
    assert proven is not None
    assert Decimal(proven.total) / 100 == expected.amount
    assert proven.count == len(expected.must_cite)

    body = client.post(
        "/api/v1/queries",
        {"question": "Which payments have no recorded award behind them?"},
        "application/json",
    ).json()
    assert body["status"] == "answered", body
    orphans = oracle.expected({"kind": "anomalies", "anomaly": "orphan_outlay"})
    assert {e["event_id"] for c in body["citations"] for e in c["events"]} == orphans.must_cite
    assert verify_citations(client, body) == 3
    assert appended == body["checkpoint_tree_size"]
    assert Decimal(body["slots"][1]["value"]) > 0
