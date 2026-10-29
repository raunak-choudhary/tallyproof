"""Compiled specs, run as the analyst over the evaluation dataset, match hand-checked answers."""

from decimal import Decimal
from typing import Any

import pytest
from django.db import transaction

from apps.analyst.compiler import compile_spec
from apps.analyst.query_spec import QuerySpec
from apps.ledger.append import Delivery, append
from apps.ledger.models import LedgerEvent
from evals.dataset import OUT_DIR
from tallyproof_pipeline.gold import read_events
from tests.integration.analyst.conftest import query

pytestmark = pytest.mark.django_db

HHS = "Department of Health and Human Services"


@pytest.fixture
def tree_size(as_analyst: None) -> int:
    events = list(read_events(OUT_DIR / "events.jsonl.gz"))
    with transaction.atomic():
        append([Delivery(e, "fin.events.raw.v1", 0, i) for i, e in enumerate(events)])
    return LedgerEvent.objects.count()


def run(
    spec: dict[str, Any], tree_size: int
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    compiled = compile_spec(QuerySpec.model_validate(spec), tree_size=tree_size, max_rows=1000)
    value = query(compiled.value_sql, *compiled.value_params) if compiled.value_sql else []
    params = list(compiled.evidence_params)
    if compiled.group_column:
        params += [[row[0] for row in value], 1000]
    return value, query(compiled.evidence_sql, *params)


def eq(field: str, value: object) -> dict[str, object]:
    return {"field": field, "op": "eq", "value": value}


def test_a_sum_matches_its_hand_checked_value_and_its_evidence(tree_size):
    filters = [eq("awarding_agency", HHS), eq("fiscal_year", 2024)]
    value, evidence = run(
        {"shape": "aggregate", "entity": "obligations", "metric": "sum_amount", "filters": filters},
        tree_size,
    )
    assert value == [(Decimal("17049347.67"), 29)]
    assert len(evidence) == 29
    assert sum(row[2] for row in evidence) == Decimal("17049347.67")


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (
            {
                "entity": "outlays",
                "metric": "sum_amount",
                "filters": [eq("awarding_agency", "Department of the Interior")],
            },
            Decimal("2681559.33"),
        ),
        (
            {
                "entity": "outlays",
                "metric": "sum_amount",
                "filters": [eq("fiscal_year", 2024), eq("fiscal_period", 2)],
            },
            Decimal("5267715.17"),
        ),
        (
            {
                "entity": "obligations",
                "metric": "count",
                "filters": [{"field": "amount", "op": "lt", "value": "0"}],
            },
            32,
        ),
        (
            {
                "entity": "obligations",
                "metric": "count",
                "filters": [
                    eq("awarding_agency", "Department of Defense"),
                    {"field": "amount", "op": "lt", "value": "0"},
                ],
            },
            15,
        ),
    ],
)
def test_hand_checked_aggregates(tree_size, spec, expected):
    value, _ = run({"shape": "aggregate", **spec}, tree_size)
    assert value[0][0] == expected


def test_the_top_agency_is_hhs(tree_size):
    value, evidence = run(
        {
            "shape": "aggregate",
            "entity": "obligations",
            "metric": "sum_amount",
            "filters": [eq("fiscal_year", 2024)],
            "group_by": "awarding_agency",
            "limit": 1,
        },
        tree_size,
    )
    assert value == [(HHS, Decimal("17049347.67"), 29)]
    assert sum(1 for row in evidence if row[2] == HHS) == 29


def test_a_lookup_and_the_largest_obligation(tree_size):
    _, rows = run(
        {
            "shape": "lookup",
            "entity": "obligations",
            "filters": [eq("piid", "SPE60524FVL5B"), eq("event_type", "obligation.adjusted")],
            "fields": ["modification_number", "action_date", "amount"],
        },
        tree_size,
    )
    assert [(r[0], r[2], str(r[3]), r[4]) for r in rows] == [
        ("evt_01HCYXR5V05A7B5BVQG6CTWM5K", "P00001", "2023-10-10", Decimal("-709.56"))
    ]
    value, rows = run(
        {"shape": "aggregate", "entity": "obligations", "metric": "max_amount"}, tree_size
    )
    assert value[0][0] == Decimal("5968992.08")
    assert rows[0][0] == "evt_01HF6H82106HHY9EFJ8GKZ5Z4F"


def test_absence_finds_exactly_the_orphan_outlays(tree_size):
    _, rows = run(
        {"shape": "absence", "entity": "outlays", "absence_rule": "outlay_without_recorded_award"},
        tree_size,
    )
    assert sorted(r[0] for r in rows) == [
        "evt_01HGQZVWJ8R4HTX3V6B840V2AE",
        "evt_01HH8GC300EFPAZ20N0Q7B6W31",
        "evt_01HKBEPS002QJ51K6KCK3HY6AF",
    ]


def test_an_earlier_checkpoint_sees_only_its_own_leaves(tree_size):
    value, evidence = run(
        {"shape": "aggregate", "entity": "obligations", "metric": "count"}, tree_size=100
    )
    assert value[0][0] == len(evidence) <= 100
    assert all(row[1] < 100 for row in evidence)


def test_award_totals_and_fields_as_of_an_earlier_checkpoint(tree_size):
    early = tree_size // 3
    _, awards = run(
        {
            "shape": "list",
            "entity": "awards",
            "limit": 100,
            "fields": ["award_key", "total_obligated", "total_outlays"],
        },
        early,
    )
    assert awards
    for _, leaf, award_key, obligated, paid in awards:
        assert leaf < early
        (expected,) = query(
            "SELECT coalesce(sum(amount), 0) FROM obligations "
            "WHERE award_key = %s AND leaf_index < %s",
            award_key,
            early,
        )[0]
        (expected_paid,) = query(
            "SELECT coalesce(sum(period_outlay), 0) FROM outlays "
            "WHERE award_key = %s AND leaf_index < %s",
            award_key,
            early,
        )[0]
        assert (obligated, paid) == (expected, expected_paid)
    _, rows = run(
        {
            "shape": "list",
            "entity": "obligations",
            "limit": 100,
            "fields": ["award_key", "awarding_agency"],
        },
        early,
    )
    for _, _, award_key, agency in rows:
        if agency is None:
            continue
        (first,) = query(
            "SELECT min(leaf_index) FROM obligations "
            "WHERE award_key = %s AND event_type = 'obligation.recorded'",
            award_key,
        )[0]
        assert first < early
