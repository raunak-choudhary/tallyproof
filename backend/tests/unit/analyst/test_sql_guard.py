"""The fallback SQL guard against the threat model's hostile-SQL corpus."""

import pytest

from apps.analyst.sql_guard import GuardError, Rejection, guard

ALLOWED = [
    "SELECT sum(amount) FROM obligations WHERE awarding_agency = 'Department of State'",
    "SELECT awarding_agency, avg(amount) AS mean FROM obligations GROUP BY awarding_agency "
    "HAVING count(*) > 2 ORDER BY mean DESC LIMIT 3",
    "SELECT o.piid, sum(p.period_outlay) AS paid FROM obligations o "
    "JOIN outlays p ON p.award_key = o.award_key GROUP BY o.piid",
    "SELECT o.piid FROM obligations o LEFT JOIN awards a USING (award_key) "
    "WHERE a.total_outlays > 0",
    "WITH big AS (SELECT * FROM obligations WHERE amount > 1000000) SELECT count(*) FROM big",
    "SELECT piid FROM obligations o WHERE NOT EXISTS "
    "(SELECT 1 FROM outlays p WHERE p.award_key = o.award_key)",
    "SELECT * FROM breaks WHERE break_type IN ('orphan_outlay', 'late_after_close') "
    "AND amount_delta BETWEEN 0 AND 100 AND award_key IS NOT NULL AND award_key ILIKE 'cont%'",
]

HOSTILE = [
    # Anything but exactly one SELECT
    ("SELECT 1 FROM obligations; DELETE FROM obligations", Rejection.NOT_ONE_SELECT),
    ("DELETE FROM obligations", Rejection.NOT_ONE_SELECT),
    ("UPDATE obligations SET amount = 0", Rejection.NOT_ONE_SELECT),
    ("INSERT INTO breaks (break_id) VALUES ('x')", Rejection.NOT_ONE_SELECT),
    ("DROP VIEW obligations", Rejection.NOT_ONE_SELECT),
    ("COPY (SELECT 1) TO '/tmp/x'", Rejection.NOT_ONE_SELECT),
    ("SET statement_timeout = 0", Rejection.NOT_ONE_SELECT),
    ("SELECT 1 FROM obligations UNION SELECT 1 FROM outlays", Rejection.NOT_ONE_SELECT),
    ("EXPLAIN ANALYZE SELECT * FROM obligations", Rejection.NOT_ONE_SELECT),
    ("WITH d AS (DELETE FROM obligations RETURNING *) SELECT * FROM d", Rejection.CONSTRUCT),
    ("this is not sql at all (", Rejection.UNPARSABLE),
    # Relations outside the views
    ("SELECT * FROM ledger_event", Rejection.RELATION),
    ("SELECT * FROM public.ledger_event", Rejection.RELATION),
    ("SELECT * FROM analyst.obligations", Rejection.RELATION),
    ("SELECT * FROM pg_catalog.pg_roles", Rejection.RELATION),
    ("SELECT * FROM pg_shadow", Rejection.RELATION),
    ("SELECT * FROM information_schema.tables", Rejection.RELATION),
    ("SELECT description FROM obligation_descriptions", Rejection.RELATION),
    ("SELECT 1", Rejection.RELATION),
    # Columns outside the views
    ("SELECT canonical_bytes FROM obligations", Rejection.COLUMN),
    ("SELECT kafka_offset FROM outlays", Rejection.COLUMN),
    ("SELECT public.obligations.amount FROM obligations", Rejection.COLUMN),
    # Functions and constructs off the allowlist
    ("SELECT pg_sleep(10) FROM obligations", Rejection.CONSTRUCT),
    ("SELECT current_setting('is_superuser') FROM obligations", Rejection.CONSTRUCT),
    ("SELECT set_config('statement_timeout', '0', false) FROM obligations", Rejection.CONSTRUCT),
    ("SELECT pg_read_file('/etc/passwd') FROM obligations", Rejection.CONSTRUCT),
    ("SELECT lo_import('/etc/passwd') FROM obligations", Rejection.CONSTRUCT),
    ("SELECT dblink('host=evil', 'SELECT 1') FROM obligations", Rejection.CONSTRUCT),
    ("SELECT * FROM generate_series(1, 1000000000)", Rejection.CONSTRUCT),
    ("SELECT * FROM obligations, LATERAL (SELECT 1) x", Rejection.CONSTRUCT),
    ("SELECT * FROM obligations FOR UPDATE", Rejection.CONSTRUCT),
    (
        "WITH RECURSIVE r AS (SELECT 1 AS n UNION ALL SELECT n + 1 FROM r) SELECT * FROM r",
        Rejection.CONSTRUCT,
    ),
    ("SELECT * FROM obligations LIMIT 10 OFFSET 5", Rejection.CONSTRUCT),
    ("SELECT * FROM obligations LIMIT (SELECT 1)", Rejection.PROJECTION),
    ("SELECT string_agg(piid, ',') FROM obligations", Rejection.CONSTRUCT),
    ("SELECT row_number() OVER () FROM obligations", Rejection.CONSTRUCT),
    # Casts
    ("SELECT 'obligations'::regclass FROM obligations", Rejection.CONSTRUCT),
    ("SELECT amount::bytea FROM obligations", Rejection.CAST),
    # Joins without an equality on allowlisted keys
    ("SELECT * FROM obligations o JOIN outlays p ON true", Rejection.JOIN),
    ("SELECT * FROM obligations o JOIN outlays p ON o.amount = p.period_outlay", Rejection.JOIN),
    ("SELECT * FROM obligations CROSS JOIN outlays", Rejection.JOIN),
    ("SELECT * FROM obligations NATURAL JOIN outlays", Rejection.JOIN),
    ("SELECT * FROM obligations o JOIN outlays p USING (fiscal_year)", Rejection.JOIN),
    # Computed output values: a number typed into SQL must never become a cited value
    (
        "SELECT event_id, leaf_index, CAST('987654321.00' AS DECIMAL) AS amount FROM obligations",
        Rejection.PROJECTION,
    ),
    ("SELECT event_id, leaf_index, amount * 1000 AS amount FROM obligations", Rejection.PROJECTION),
    (
        "SELECT CASE WHEN amount < 0 THEN 'down' ELSE 'up' END AS d, count(*) FROM obligations GROUP BY 1",
        Rejection.PROJECTION,
    ),
    ("SELECT round(sum(amount), 2) FROM obligations", Rejection.PROJECTION),
    (
        "SELECT o.event_id, p.leaf_index, p.period_outlay FROM obligations o JOIN outlays p ON o.award_key = p.award_key",
        Rejection.PROJECTION,
    ),
    ("SELECT amount::double FROM obligations", Rejection.CAST),
    # CTE shadowing: a name must resolve the way Postgres resolves it
    (
        "WITH x AS (WITH pg_stat_activity AS (SELECT event_id FROM obligations) SELECT event_id FROM pg_stat_activity) SELECT * FROM pg_stat_activity",
        Rejection.CONSTRUCT,
    ),
    (
        "WITH obligation_descriptions AS (SELECT * FROM obligation_descriptions) SELECT * FROM obligation_descriptions",
        Rejection.RELATION,
    ),
    (
        "WITH a AS (SELECT * FROM b), b AS (SELECT * FROM obligations) SELECT * FROM a",
        Rejection.RELATION,
    ),
    (
        "SELECT * FROM obligations WHERE event_id IN (WITH pg_roles AS (SELECT event_id FROM obligations) SELECT event_id FROM pg_roles)",
        Rejection.CONSTRUCT,
    ),
    # Joins that compare a key with itself, or hide behind OR, are cartesian
    (
        "SELECT a.piid FROM obligations a JOIN outlays b ON a.award_key = a.award_key",
        Rejection.JOIN,
    ),
    (
        "SELECT a.piid FROM obligations a JOIN outlays b ON a.award_key = b.award_key OR TRUE",
        Rejection.JOIN,
    ),
    ("SELECT a.piid FROM obligations a JOIN outlays b ON award_key = award_key", Rejection.JOIN),
    # Size
    ("SELECT " + " + ".join(["amount"] * 300) + " FROM obligations", Rejection.TOO_COMPLEX),
    ("SELECT " + "(" * 40 + "amount" + ")" * 40 + " FROM obligations", Rejection.TOO_COMPLEX),
    ("SELECT amount FROM obligations WHERE piid = '" + "x" * 5000 + "'", Rejection.TOO_COMPLEX),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_ordinary_analytics_is_allowed(sql):
    guarded = guard(sql, max_rows=50)
    assert guarded.sql.rstrip().endswith(("LIMIT 50", "LIMIT 3"))


@pytest.mark.parametrize(("sql", "code"), HOSTILE)
def test_hostile_sql_is_refused_with_a_generic_code(sql, code):
    with pytest.raises(GuardError) as caught:
        guard(sql, max_rows=50)
    assert caught.value.code == code
    assert str(caught.value) == code.value  # never the SQL itself


def test_the_sql_that_runs_is_rebuilt_from_the_tree():
    guarded = guard("select  piid  from obligations -- comment\n where amount<0", max_rows=7)
    assert guarded.sql == "SELECT piid FROM obligations WHERE amount < 0 LIMIT 7"
    assert guarded.relations == {"obligations"}


def test_a_larger_limit_is_tightened_and_a_smaller_one_kept():
    assert guard("SELECT piid FROM obligations LIMIT 999", max_rows=10).sql.endswith("LIMIT 10")
    assert guard("SELECT piid FROM obligations LIMIT 3", max_rows=10).sql.endswith("LIMIT 3")


def test_every_view_is_pinned_to_the_checkpoint():
    sql = guard(
        "SELECT o.event_id, o.leaf_index, o.piid FROM obligations o "
        "JOIN outlays p ON p.award_key = o.award_key",
        max_rows=10,
        tree_size=500,
    ).sql
    assert "o.leaf_index < 500" in sql
    assert "p.leaf_index < 500" in sql
    nested = guard(
        "SELECT piid FROM obligations o WHERE NOT EXISTS "
        "(SELECT 1 FROM outlays p WHERE p.award_key = o.award_key)",
        max_rows=10,
        tree_size=7,
    ).sql
    assert nested.count("< 7") == 2
    breaks = guard("SELECT break_id, break_type FROM breaks", max_rows=10, tree_size=9).sql
    assert "found_at_leaf_index < 9" in breaks
