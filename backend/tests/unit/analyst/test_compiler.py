from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.analyst.compiler import compile_spec
from apps.analyst.query_spec import CATALOG, LOOKUP_ROWS, MAX_LIST_ROWS, QuerySpec


def spec(**kwargs: object) -> QuerySpec:
    return QuerySpec.model_validate(kwargs)


def hhs(**extra: object) -> QuerySpec:
    return spec(
        shape="aggregate",
        entity="obligations",
        metric="sum_amount",
        filters=[
            {
                "field": "awarding_agency",
                "op": "eq",
                "value": "Department of Health and Human Services",
            },
            {"field": "fiscal_year", "op": "eq", "value": 2024},
        ],
        **extra,
    )


def test_an_aggregate_binds_every_value_and_pins_the_checkpoint():
    q = compile_spec(hhs(), tree_size=717, max_rows=1000)
    assert q.value_sql == (
        'SELECT coalesce(sum(t."amount"), 0) AS value, count(*) AS row_count '
        'FROM analyst."obligations" t WHERE t."leaf_index" < %s '
        'AND t."award_leaf_index" < %s '
        'AND t."awarding_agency" = %s AND t."fiscal_year" = %s'
    )
    assert q.value_params == [717, 717, "Department of Health and Human Services", 2024]
    assert q.evidence_sql.startswith('SELECT t."event_id", t."leaf_index", t."amount" FROM')
    assert q.evidence_sql.endswith('ORDER BY t."leaf_index" LIMIT 1001')
    assert q.words == (
        "total of obligations and modifications where awarding agency is "
        "Department of Health and Human Services and fiscal year is 2024"
    )


def test_values_are_parsed_into_their_types_and_shown_in_words():
    q = compile_spec(
        spec(
            shape="list",
            entity="obligations",
            filters=[
                {"field": "amount", "op": "lt", "value": "0"},
                {"field": "action_date", "op": "gte", "value": "2023-10-01"},
                {"field": "awarding_agency", "op": "in", "value": ["A", "B"]},
                {"field": "piid", "op": "ne", "value": "X"},
            ],
            fields=["piid", "amount"],
            order_by="amount",
            descending=False,
            limit=5,
        ),
        tree_size=10,
        max_rows=100,
    )
    assert q.evidence_params == [10, 10, Decimal(0), date(2023, 10, 1), ["A", "B"], "X"]
    assert 't."awarding_agency" = ANY(%s)' in q.evidence_sql
    assert 't."piid" IS DISTINCT FROM %s' in q.evidence_sql
    assert 'ORDER BY t."amount" ASC NULLS LAST, t."leaf_index" LIMIT 5' in q.evidence_sql
    assert q.words == (
        "obligations and modifications where amount is below 0.00 and action date is at least "
        "2023-10-01 and awarding agency is one of A, B and contract number (PIID) is not X, "
        "5 smallest by amount"
    )


def test_a_grouped_top_n_ranks_groups_and_cites_their_rows():
    q = compile_spec(hhs(group_by="awarding_agency", limit=1), tree_size=5, max_rows=10)
    assert q.value_sql is not None
    assert 'GROUP BY t."awarding_agency" ORDER BY value DESC NULLS LAST, grp LIMIT 1' in q.value_sql
    assert q.group_column == "grp"
    assert "by awarding agency, top 1 by total" in q.words
    # A record with no agency isn't a group, and the reader is told it was left out.
    assert 't."awarding_agency" IS NOT NULL' in q.value_sql
    assert 't."awarding_agency" IS NOT NULL' in q.evidence_sql
    assert q.words.endswith("leaving out records with no awarding agency")
    # Evidence comes per returned group: the caller adds the groups and a per-group cap.
    assert 't."awarding_agency" = ANY(%s)' in q.evidence_sql
    assert "PARTITION BY" in q.evidence_sql
    assert q.evidence_sql.count("%s") == len(q.evidence_params) + 2


@pytest.mark.parametrize(
    ("extra", "words"),
    [
        ({}, "obligations and modifications, the latest 5 in log order"),
        ({"descending": False}, "obligations and modifications, the first 5 in log order"),
        (
            {"order_by": "amount", "descending": True},
            "obligations and modifications, 5 largest by amount",
        ),
        (
            {"order_by": "amount", "descending": False},
            "obligations and modifications, 5 smallest by amount",
        ),
    ],
)
def test_list_wording_follows_the_order(extra, words):
    q = compile_spec(
        spec(shape="list", entity="obligations", limit=5, **extra), tree_size=5, max_rows=10
    )
    assert q.words == words


def test_an_unranked_grouping_fetches_one_group_past_the_cap():
    q = compile_spec(hhs(group_by="awarding_agency"), tree_size=5, max_rows=10)
    assert q.value_sql is not None
    assert q.value_sql.endswith(f"LIMIT {MAX_LIST_ROWS + 1}")


def test_min_and_max_cite_the_extreme_row():
    q = compile_spec(
        spec(shape="aggregate", entity="obligations", metric="max_amount", fields=["piid"]),
        tree_size=5,
        max_rows=10,
    )
    assert q.evidence_sql.startswith('SELECT t."event_id", t."leaf_index", t."amount", t."piid"')
    assert 't."amount" IS NOT NULL' in q.evidence_sql
    assert q.evidence_sql.endswith('ORDER BY t."amount" DESC NULLS LAST, t."leaf_index" LIMIT 1')
    assert q.words == "largest of obligations and modifications"


def test_a_lookup_fetches_one_row_past_its_cap_so_ambiguity_shows():
    q = compile_spec(
        spec(
            shape="lookup",
            entity="obligations",
            filters=[{"field": "piid", "op": "eq", "value": "SPE60524FVL5B"}],
            fields=["modification_number", "amount"],
        ),
        tree_size=5,
        max_rows=10,
    )
    assert q.evidence_sql.endswith(f"LIMIT {LOOKUP_ROWS + 1}")
    assert q.evidence_limit == LOOKUP_ROWS + 1


def test_absence_names_its_rule():
    q = compile_spec(
        spec(shape="absence", entity="outlays", absence_rule="outlay_without_recorded_award"),
        tree_size=5,
        max_rows=10,
    )
    assert "NOT EXISTS (SELECT 1 FROM analyst.obligations b" in q.evidence_sql
    assert q.evidence_sql.count("%s") == 2  # the rule looks only at leaves the checkpoint covers
    assert q.evidence_params == [5, 5]
    assert q.words == "outlay reports with no recorded obligation for their award"


def test_breaks_are_pinned_by_the_leaf_that_found_them():
    q = compile_spec(
        spec(shape="aggregate", entity="breaks", metric="count"), tree_size=5, max_rows=10
    )
    assert 't."found_at_leaf_index" < %s' in (q.value_sql or "")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"shape": "aggregate", "entity": "ledger_event", "metric": "count"}, "entity"),
        ({"shape": "aggregate", "entity": "obligations", "metric": "avg"}, "metric"),
        ({"shape": "aggregate", "entity": "obligations"}, "needs a metric"),
        ({"shape": "aggregate", "entity": "journal", "metric": "sum_amount"}, "no amount"),
        (
            {"shape": "aggregate", "entity": "obligations", "metric": "count", "fields": ["piid"]},
            "only a min or max",
        ),
        (
            {"shape": "aggregate", "entity": "obligations", "metric": "count", "limit": 3},
            "only a grouped aggregate",
        ),
        (
            {"shape": "aggregate", "entity": "obligations", "metric": "count", "group_by": "piid"},
            "can't be grouped",
        ),
        (
            {
                "shape": "list",
                "entity": "obligations",
                "limit": 5,
                "filters": [{"field": "description", "op": "eq", "value": "x"}],
            },
            "no field 'description'",
        ),
        (
            {
                "shape": "list",
                "entity": "obligations",
                "limit": 5,
                "filters": [{"field": "amount", "op": "eq", "value": "1; DROP TABLE x"}],
            },
            "not a valid money",
        ),
        (
            {
                "shape": "list",
                "entity": "obligations",
                "limit": 5,
                "filters": [{"field": "fiscal_year", "op": "in", "value": 2024}],
            },
            "'in' takes a list",
        ),
        (
            {
                "shape": "list",
                "entity": "obligations",
                "limit": 5,
                "filters": [{"field": "amount", "op": "like", "value": "1"}],
            },
            "op",
        ),
        ({"shape": "list", "entity": "obligations"}, "needs a limit"),
        ({"shape": "list", "entity": "obligations", "limit": 0}, "greater than or equal"),
        ({"shape": "lookup", "entity": "obligations"}, "needs filters"),
        ({"shape": "absence", "entity": "outlays"}, "needs a rule"),
        (
            {
                "shape": "absence",
                "entity": "awards",
                "absence_rule": "outlay_without_recorded_award",
            },
            "only absence rule",
        ),
        ({"shape": "list", "entity": "obligations", "limit": 5, "sql": "SELECT 1"}, "Extra inputs"),
    ],
)
def test_specs_outside_the_catalog_are_rejected(kwargs, message):
    with pytest.raises(ValidationError, match=message):
        QuerySpec.model_validate(kwargs)


def test_every_catalog_name_is_a_plain_identifier():
    for entity in CATALOG.values():
        for name in (entity.view, entity.id_column, entity.leaf_column, *entity.fields):
            assert name.replace("_", "").isalnum()
            assert name.islower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", "1e100000000000000"),
        ("amount", "-1e17"),
        ("amount", "100000000000000000"),
        ("amount", "1" * 40),
        ("amount", "1e-100000000000000"),
        ("amount", "0.001"),
        ("fiscal_year", 2**63),
        ("fiscal_year", "9" * 30),
    ],
)
def test_values_past_the_column_range_are_rejected(field, value):
    spec = {
        "shape": "list",
        "entity": "obligations",
        "limit": 5,
        "filters": [{"field": field, "op": "eq", "value": value}],
    }
    with pytest.raises(ValidationError, match=r"out of range|not a valid"):
        QuerySpec.model_validate(spec)


def test_the_largest_amount_a_column_holds_is_accepted():
    spec = QuerySpec.model_validate({
        "shape": "list",
        "entity": "obligations",
        "limit": 5,
        "filters": [{"field": "amount", "op": "gte", "value": "99999999999999999.99"}],
    })  # fmt: skip
    assert spec.filters[0].value == "99999999999999999.99"


def test_award_fields_count_only_awards_recorded_before_the_checkpoint():
    q = hhs()
    compiled = compile_spec(q, tree_size=5, max_rows=10)
    assert 't."award_leaf_index" < %s' in compiled.evidence_sql
    assert compiled.value_sql is not None
    assert 't."award_leaf_index" < %s' in compiled.value_sql
    assert compiled.value_params.count(5) == 2
    plain = compile_spec(
        spec(shape="aggregate", entity="obligations", metric="count"), tree_size=5, max_rows=10
    )
    assert "award_leaf_index" not in plain.evidence_sql


def test_award_totals_are_built_only_from_leaves_before_the_checkpoint():
    q = compile_spec(
        spec(
            shape="list",
            entity="awards",
            limit=5,
            order_by="total_obligated",
            descending=True,
            filters=[{"field": "piid", "op": "eq", "value": "X1"}],
        ),
        tree_size=7,
        max_rows=10,
    )
    assert "analyst.awards" not in q.evidence_sql
    assert q.evidence_sql.count("< %s") == 4
    # The derived table reads three pinned sources before the outer WHERE.
    assert q.evidence_params[:4] == [7, 7, 7, 7]
    assert q.evidence_params[-1] == "X1"
