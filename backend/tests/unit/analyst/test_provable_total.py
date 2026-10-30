"""Which totals the signed sum tree can prove (ADR-0024)."""

from typing import Any

import pytest

from apps.analyst.answer import ProvableTotal, provable_total
from apps.analyst.query_spec import QuerySpec

ENERGY = {"field": "awarding_agency", "op": "eq", "value": "Department of Energy"}
FY24 = {"field": "fiscal_year", "op": "eq", "value": 2024}


def spec(**fields: Any) -> QuerySpec:
    return QuerySpec.model_validate({"shape": "aggregate", "metric": "sum_amount", **fields})


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"entity": "obligations"}, ProvableTotal("obligations")),
        (
            {"entity": "outlays", "filters": [ENERGY]},
            ProvableTotal("outlays", "Department of Energy"),
        ),
        (
            {"entity": "obligations", "filters": [FY24, ENERGY]},
            ProvableTotal("obligations", "Department of Energy", 2024),
        ),
        (
            {"entity": "obligations", "metric": "count", "filters": [ENERGY]},
            ProvableTotal("obligations", "Department of Energy"),
        ),
    ],
)
def test_totals_the_tree_can_prove(fields: dict[str, Any], expected: ProvableTotal) -> None:
    assert provable_total(spec(**fields)) == expected


@pytest.mark.parametrize(
    "fields",
    [
        {"entity": "obligations", "filters": [FY24]},  # a year across every agency
        {
            "entity": "obligations",
            "filters": [{"field": "naics_code", "op": "eq", "value": "541511"}],
        },
        {"entity": "obligations", "filters": [{**ENERGY, "op": "ne"}]},
        {"entity": "obligations", "filters": [ENERGY, {**ENERGY, "value": "Department of Labor"}]},
        {"entity": "obligations", "metric": "max_amount"},
        {"entity": "obligations", "group_by": "awarding_agency"},
        {"entity": "awards"},
    ],
)
def test_totals_it_cannot_prove_keep_the_labelled_sample(fields: dict[str, Any]) -> None:
    assert provable_total(spec(**fields)) is None


def test_lists_and_lookups_have_no_total() -> None:
    listing = QuerySpec.model_validate({"shape": "list", "entity": "obligations", "limit": 5})
    assert provable_total(listing) is None
