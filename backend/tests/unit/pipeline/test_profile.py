from decimal import Decimal

import pytest

from tallyproof_pipeline.profile import profile
from tests.unit.pipeline.test_gold_build import SCHEMA, silver_rows

pytestmark = pytest.mark.spark


def test_profile_counts_nulls_signs_and_categories(spark):
    rows = silver_rows()
    rows[0]["federal_action_obligation"] = Decimal("-50.00")
    rows[1]["federal_action_obligation"] = Decimal("0.00")
    rows[2]["federal_action_obligation"] = None
    frame = spark.createDataFrame([tuple(r[c] for c in SCHEMA.names) for r in rows], SCHEMA)
    result = profile(frame)
    assert result.rows == 30
    assert result.rows_by_fiscal_year == {"2025": 30}
    assert result.null_rate["federal_action_obligation"] == round(1 / 30, 6)
    assert result.null_rate["contract_transaction_unique_key"] == 0.0
    assert result.null_rate["naics_code"] == 1.0  # never set in the fixture
    assert (result.amounts["negative_rows"], result.amounts["zero_rows"]) == ("1", "1")
    assert result.amounts["positive_rows"] == "27"
    assert result.amounts["min"] == "-50.00"
    assert list(result.amount_quantiles) == ["p1", "p10", "p25", "p50", "p75", "p90", "p99"]
    assert result.top_awarding_agencies == [("Department of Energy", 30)]
