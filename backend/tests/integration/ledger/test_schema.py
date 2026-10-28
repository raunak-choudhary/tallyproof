import importlib
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg import errors

from tallyproof_core.events import EventEnvelope
from tallyproof_core.ids import new_id

INSERT = """
INSERT INTO ledger_event (public_id, leaf_index, idempotency_key, event_type, account_id,
  occurred_at, emitted_at, canonical_bytes, leaf_hash, kafka_topic, kafka_partition,
  kafka_offset, correlation_id)
VALUES (%(public_id)s, %(leaf_index)s, %(idempotency_key)s, %(event_type)s, %(account_id)s,
  %(occurred_at)s, %(emitted_at)s, %(canonical_bytes)s, %(leaf_hash)s, 'fin.events.raw.v1', 0,
  %(leaf_index)s, '')
"""


def event(amount: str = "1250.00", key: str | None = None) -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "event_id": new_id("evt"),
            "idempotency_key": key or f"test:{new_id('src')}",
            "event_type": "obligation.recorded",
            "occurred_at": datetime(2025, 1, 2, tzinfo=UTC),
            "emitted_at": datetime(2025, 1, 3, tzinfo=UTC),
            "account_id": "ZQGGHJH74DW7",
            "correlation_id": "c-1",
            "payload": {
                "award_key": "CONT_AWD_A1",
                "piid": "PIID1",
                "awarding_agency": "Department of Energy",
                "amount": amount,
                "action_date": "2025-01-02",
            },
        }
    )


def row(e: EventEnvelope, leaf_index: int = 0, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "public_id": e.event_id,
        "leaf_index": leaf_index,
        "idempotency_key": e.idempotency_key,
        "event_type": e.event_type.value,
        "account_id": e.account_id,
        "occurred_at": e.occurred_at,
        "emitted_at": e.emitted_at,
        "canonical_bytes": e.canonical_bytes(),
        "leaf_hash": e.leaf_hash(),
    }
    return {**values, **overrides}


def test_app_appends_an_event_and_the_payload_is_derived_from_its_bytes(migrated):
    e = event()
    with migrated.connect("app") as conn:
        conn.execute(INSERT, row(e))
        payload, stored_hash = conn.execute(
            "SELECT payload, leaf_hash FROM ledger_event WHERE public_id = %s", [e.event_id]
        ).fetchone()
    assert payload == e.payload.model_dump(mode="json", exclude_none=True)
    assert bytes(stored_hash) == e.leaf_hash()


def test_a_leaf_hash_that_does_not_match_the_bytes_is_refused(migrated):
    with migrated.connect("app") as conn, pytest.raises(errors.CheckViolation, match="leaf_hash"):
        conn.execute(INSERT, row(event(), leaf_hash=bytes(32)))


@pytest.mark.parametrize("column", ["public_id", "idempotency_key", "event_type", "account_id"])
def test_columns_that_disagree_with_the_hashed_document_are_refused(migrated, column):
    e = event()
    wrong = {
        "public_id": new_id("evt"),
        "idempotency_key": "test:other",
        "event_type": "outlay.reported",
        "account_id": "OTHER",
    }[column]
    values = row(e)
    values[column] = wrong
    with migrated.connect("app") as conn, pytest.raises(errors.CheckViolation, match="document"):
        conn.execute(INSERT, values)


def test_idempotency_key_and_leaf_index_are_unique(migrated):
    first = event(key="test:same")
    with migrated.connect("app") as conn:
        conn.execute(INSERT, row(first, 0))
        with pytest.raises(errors.UniqueViolation, match="idempotency_key"):
            conn.execute(INSERT, row(event(key="test:same"), 1))
        with pytest.raises(errors.UniqueViolation, match="leaf_index"):
            conn.execute(INSERT, row(event(), 0))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledger_event SET correlation_id = 'x'",
        "DELETE FROM ledger_event",
        "TRUNCATE ledger_event",
        "UPDATE ledger_batch SET key_id = 'x'",
        "DELETE FROM dedupe_rejection",
    ],
)
def test_the_app_role_cannot_change_append_only_tables(migrated, statement):
    with migrated.connect("app") as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute(statement)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledger_event SET correlation_id = 'x'",
        "DELETE FROM ledger_event",
        "TRUNCATE ledger_event",
    ],
)
def test_triggers_stop_even_the_owner(migrated, statement):
    with migrated.connect("app") as conn:
        conn.execute(INSERT, row(event()))
    with (
        migrated.connect("owner") as conn,
        pytest.raises(errors.InsufficientPrivilege, match="append-only"),
    ):
        conn.execute(statement)


def test_the_log_head_is_a_single_row_the_app_can_only_advance(migrated):
    with migrated.connect("app") as conn:
        conn.execute("UPDATE merkle_log_head SET next_leaf_index = next_leaf_index + 5")
        assert conn.execute("SELECT id, next_leaf_index FROM merkle_log_head").fetchall() == [
            (1, 5)
        ]
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("INSERT INTO merkle_log_head (id, next_leaf_index) VALUES (2, 0)")
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("UPDATE merkle_log_head SET id = 2")
    with (
        migrated.connect("owner") as conn,
        pytest.raises(errors.CheckViolation, match="single_row"),
    ):
        conn.execute("INSERT INTO merkle_log_head (id, next_leaf_index) VALUES (2, 0)")


def test_the_app_tracks_consumer_offsets_but_cannot_delete_them(migrated):
    with migrated.connect("app") as conn:
        conn.execute(
            """
            INSERT INTO consumer_offset (consumer_group, topic, partition, next_offset, generation)
            VALUES ('g', 't', 0, 10, 1)
            ON CONFLICT (consumer_group, topic, partition) DO UPDATE
              SET next_offset = GREATEST(consumer_offset.next_offset, EXCLUDED.next_offset)
            """
        )
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("DELETE FROM consumer_offset")


def test_the_analyst_cannot_read_ledger_tables_or_write_anything(migrated):
    with migrated.connect("analyst") as conn:
        assert conn.execute("SHOW search_path").fetchone() == ("analyst",)
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("SELECT 1 FROM public.ledger_event")
    with migrated.connect("analyst") as conn, pytest.raises(errors.ReadOnlySqlTransaction):
        conn.execute("CREATE TABLE analyst.x (i int)")


def test_nobody_else_can_connect(migrated):
    url = migrated.url("superuser")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("CREATE ROLE stranger LOGIN PASSWORD 'stranger'")
    stranger = url.replace(f"postgres:{migrated.passwords['superuser']}", "stranger:stranger")
    with pytest.raises(psycopg.OperationalError, match="permission denied"):
        psycopg.connect(stranger)


def test_the_grants_can_be_applied_again(migrated):
    grants = importlib.import_module("apps.ledger.migrations.0004_role_grants")
    with migrated.connect("owner") as conn:
        conn.execute(grants.FORWARD)
        conn.execute(grants.FORWARD)
