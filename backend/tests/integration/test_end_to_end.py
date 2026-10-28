"""From real events to verified proofs, through real Redpanda and Postgres.

Real USAspending events from the committed sample are published with the replay
producer, a few of them twice and a few deliberately invalid. The ingestion loop
consumes them with a real Kafka consumer, the checkpointer signs, and every
proof the API returns is checked here with the core verifier.
"""

import json
import random
import time
from itertools import islice

import pytest
from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from django.db import connection
from django.test import Client
from testcontainers.community.kafka import RedpandaContainer

from apps.ingestion.consumer import Ingestor, run
from apps.ingestion.dedupe import PartitionFilters
from apps.ledger.api import proofs
from apps.ledger.checkpointer import Checkpointer
from tallyproof_core.checkpoint import Verifier
from tallyproof_core.hashing import leaf_hash
from tallyproof_core.merkle import verify_inclusion
from tallyproof_pipeline.gold import read_events
from tallyproof_pipeline.settings import REPO_ROOT
from tallyproof_pipeline.stream import Outgoing, interleave, publish
from tests.unit.pipeline.test_replay_bundle import SIGNER

pytestmark = pytest.mark.django_db
RAW, DLQ, GROUP = "fin.events.raw.v1", "fin.events.dlq.v1", "ingest-e2e"
EVENTS, REDELIVERED, INVALID = 500, 50, 3
IPV4 = {"broker.address.family": "v4"}


@pytest.fixture(scope="module")
def broker(redpanda: RedpandaContainer) -> str:
    servers = redpanda.get_bootstrap_server()
    admin = AdminClient({"bootstrap.servers": servers, **IPV4})
    for future in admin.create_topics([NewTopic(RAW, 3, 1), NewTopic(DLQ, 1, 1)]).values():
        future.result(timeout=30)
    return servers


def messages() -> list[Outgoing]:
    sample = REPO_ROOT / "testdata" / "sample" / "gold_events_sample.jsonl.gz"
    events = list(islice(read_events(sample), EVENTS))
    invalid = []
    for source in events[100 : 100 + INVALID]:
        record = json.loads(source.model_dump_json())
        record["payload"]["amount"] = 12.5  # money as a float: refused
        invalid.append(record)
    stream = list(interleave(events, invalid))
    return stream + [m for m in stream if m.valid][:REDELIVERED]


def test_events_flow_from_kafka_to_verified_proofs(broker, migrated):
    producer = Producer({"bootstrap.servers": broker, "acks": "all", **IPV4})
    summary = publish(messages(), producer, RAW, rate_per_sec=5000)
    assert (summary.events, summary.invalid) == (EVENTS + REDELIVERED, INVALID)

    ingestor = Ingestor(
        GROUP, DLQ, Producer({"bootstrap.servers": broker, **IPV4}), PartitionFilters(10_000, 0.001)
    )
    consumer = Consumer(
        {
            "bootstrap.servers": broker,
            "group.id": GROUP,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
            **IPV4,
        }
    )
    deadline = time.monotonic() + 90
    totals = ingestor.totals
    expected = EVENTS + REDELIVERED + INVALID

    def done() -> bool:
        seen = totals.appended + totals.duplicates + totals.dead_lettered
        return seen >= expected or time.monotonic() > deadline

    run(ingestor, consumer, RAW, max_batch=100, should_stop=done)
    assert (totals.appended, totals.duplicates, totals.dead_lettered) == (
        EVENTS,
        REDELIVERED,
        INVALID,
    )
    assert ingestor.filters.stats.false_positives == 0

    with connection.cursor() as cursor:
        cursor.execute("SELECT array_agg(leaf_index ORDER BY leaf_index) FROM ledger_event")
        assert cursor.fetchone()[0] == list(range(EVENTS))
        cursor.execute(
            "SELECT sum(next_offset) FROM consumer_offset WHERE consumer_group = %s", [GROUP]
        )
        assert cursor.fetchone()[0] == expected

    dead = Consumer(
        {
            "bootstrap.servers": broker,
            "group.id": "dlq-check",
            "auto.offset.reset": "earliest",
            **IPV4,
        }
    )
    dead.subscribe([DLQ])
    letters = [m for m in dead.consume(num_messages=10, timeout=15) if m.error() is None]
    dead.close()
    assert len(letters) == INVALID
    assert all(json.loads(m.value() or b"{}")["error"] == "schema_invalid" for m in letters)

    Checkpointer(SIGNER, 256, 2000).close()
    proofs.reset()
    client = Client(HTTP_HOST="localhost")
    verifier = Verifier.from_verifier_key(SIGNER.verifier_key())
    events = client.get("/api/v1/events?limit=200").json()["results"]
    for event in random.Random(7).sample(events, 25):
        proof = client.get(f"/api/v1/events/{event['event_id']}/proof").json()
        checkpoint = verifier.verify_checkpoint(proof["checkpoint_note"])
        assert checkpoint.tree_size == EVENTS
        path = [bytes.fromhex(h) for h in proof["audit_path_hex"]]
        leaf = leaf_hash(event["canonical"].encode())
        assert verify_inclusion(leaf, event["leaf_index"], EVENTS, path, checkpoint.root_hash)
