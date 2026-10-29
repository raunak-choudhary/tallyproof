"""The analyst's curated views: what they show, and what the role can never do."""

from decimal import Decimal
from importlib import import_module

import pytest
from django.db import transaction
from psycopg import errors

from apps.analyst.sql_guard import VIEW_COLUMNS, guard
from apps.ledger.append import Delivery, append
from apps.ledger.projections import JournalProjection, catch_up
from apps.reconciliation.projection import ReconciliationProjection
from tallyproof_pipeline.overlay import Anomaly, inject
from tests.integration.analyst.conftest import query
from tests.unit.pipeline.test_overlay import cash_event, real_events

pytestmark = pytest.mark.django_db

VIEWS = {
    "awards",
    "break_events",
    "breaks",
    "cash_movements",
    "journal",
    "obligation_descriptions",
    "obligations",
    "outlays",
    "policy_sections",
}
HIDDEN = {"canonical_bytes", "leaf_hash", "kafka_topic", "kafka_offset", "correlation_id", "id"}


@pytest.fixture
def ledger(as_analyst):
    result = inject([*real_events(), cash_event()], seed=42, per_anomaly=2)
    with transaction.atomic():
        append([Delivery(e, "fin.events.raw.v1", 0, i) for i, e in enumerate(result.events)])
    catch_up(JournalProjection())
    catch_up(ReconciliationProjection())
    return result


def test_every_view_exists_and_exposes_citable_ids_but_no_internals(ledger):
    columns: dict[str, set[str]] = {}
    for view, column in query(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'analyst'"
    ):
        columns.setdefault(view, set()).add(column)
    assert set(columns) == VIEWS
    for view, names in columns.items():
        assert names & {"event_id", "break_id"}, view
        assert not names & HIDDEN, view
    assert "description" not in columns["obligations"]


def test_obligations_match_the_events_they_cite(ledger):
    rows = query(
        "SELECT event_id, amount, action_date, fiscal_year, awarding_agency FROM obligations"
    )
    obligations = [e for e in ledger.events if e.event_type.value.startswith("obligation.")]
    # Injected duplicate submissions reuse an idempotency key, so the ledger refuses them.
    assert len(rows) == len({e.idempotency_key for e in obligations})
    by_id = {e.event_id: e.payload for e in obligations}
    for event_id, amount, action_date, fiscal_year, agency in rows:
        assert amount == Decimal(by_id[event_id].amount)
        assert action_date == by_id[event_id].action_date
        assert fiscal_year == action_date.year + (action_date.month >= 10)
        assert agency == "Department of Energy"


def test_award_totals_are_the_sum_of_their_obligations(ledger):
    for award_key, total in query("SELECT award_key, total_obligated FROM awards"):
        (expected,) = query("SELECT sum(amount) FROM obligations WHERE award_key = %s", award_key)[
            0
        ]
        assert total == expected


def test_breaks_list_the_events_involved(ledger):
    labeled = {x.event_id for x in ledger.labels if x.anomaly == Anomaly.DEOBLIGATION_EXCEEDS_AWARD}
    cited = {
        event_id
        for (event_id,) in query(
            "SELECT be.event_id FROM breaks b JOIN break_events be USING (break_id) "
            "WHERE b.break_type = 'deobligation_exceeds_award'"
        )
    }
    assert labeled <= cited


def test_cash_and_journal_rows_are_visible(ledger):
    assert query("SELECT count(*) FROM cash_movements")[0][0] == 1
    debit, credit = query("SELECT sum(debit), sum(credit) FROM journal")[0]
    assert debit == credit > 0


def test_the_analyst_cannot_read_tables_behind_the_views(as_analyst):
    with pytest.raises(Exception, match="permission denied"), transaction.atomic():
        query("SELECT count(*) FROM public.ledger_event")


def test_the_analyst_cannot_write_even_with_read_only_mode_switched_off(migrated):
    """The read-only default is one layer. The grants alone still refuse every write."""
    statements = [
        "INSERT INTO analyst.breaks (break_id) VALUES ('brk_x')",
        "DELETE FROM analyst.obligations",
        "INSERT INTO public.ledger_event (public_id) VALUES ('evt_x')",
        "UPDATE public.recon_break SET detail = ''",
        "CREATE TABLE analyst.x (i int)",
        "CREATE TABLE public.x (i int)",
    ]
    for sql in statements:
        with migrated.connect("analyst") as conn:
            conn.execute("SET default_transaction_read_only = off")
            with pytest.raises((errors.InsufficientPrivilege, errors.ObjectNotInPrerequisiteState)):
                conn.execute(sql)


def test_the_guard_knows_exactly_the_columns_each_view_has(as_analyst):
    columns: dict[str, set[str]] = {}
    for view, column in query(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'analyst'"
    ):
        columns.setdefault(view, set()).add(column)
    for view, allowed in VIEW_COLUMNS.items():
        assert columns[view] == allowed, view


def test_guarded_sql_runs_as_the_analyst(ledger):
    guarded = guard(
        "SELECT o.awarding_agency, count(*) AS n FROM obligations o GROUP BY o.awarding_agency",
        max_rows=10,
        tree_size=10**9,
    )
    (total,) = query("SELECT count(*) FROM obligations")[0]
    assert query(guarded.sql) == [("Department of Energy", total)]


def test_the_award_leaf_migration_reverses_cleanly(migrated):
    award_leaf = import_module("apps.analyst.migrations.0005_award_leaf_index")
    columns = (
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'analyst' AND column_name = 'award_leaf_index' ORDER BY 1"
    )
    with migrated.connect("superuser") as conn, conn.transaction(force_rollback=True):
        conn.execute(award_leaf.REVERSE)
        assert conn.execute(columns).fetchall() == []
        conn.execute("SET LOCAL ROLE tallyproof_analyst")
        assert conn.execute("SELECT count(*) FROM analyst.awards").fetchone() == (0,)
        conn.execute("RESET ROLE")
        conn.execute(award_leaf.FORWARD)
        assert conn.execute(columns).fetchall() == [("obligations",), ("outlays",)]
