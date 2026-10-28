from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import (
    DateType,
    DecimalType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from tallyproof_pipeline.quality import (
    QualityError,
    deequ_session,
    fiscal_year_bounds,
    run_checks,
    stop_session,
)
from tallyproof_pipeline.settings import PipelineSettings

pytestmark = pytest.mark.spark

SCHEMA = StructType(
    [
        StructField("contract_transaction_unique_key", StringType()),
        StructField("contract_award_unique_key", StringType()),
        StructField("recipient_uei", StringType()),
        StructField("awarding_agency_name", StringType()),
        StructField("action_date", DateType()),
        StructField("action_date_fiscal_year", IntegerType()),
        StructField("federal_action_obligation", DecimalType(19, 2)),
    ]
)


def good_row(key: str, **overrides: Any) -> tuple[Any, ...]:
    values = {
        "contract_transaction_unique_key": key,
        "contract_award_unique_key": f"CONT_AWD_{key}",
        "recipient_uei": "ZQGGHJH74DW7",
        "awarding_agency_name": "Department of Energy",
        "action_date": date(2025, 3, 14),
        "action_date_fiscal_year": 2025,
        "federal_action_obligation": Decimal("1250.50"),
    }
    values.update(overrides)
    return tuple(values[field.name] for field in SCHEMA.fields)


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    settings = PipelineSettings(
        _env_file=None,
        DATA_DIR=tmp_path_factory.mktemp("data"),
        DATA_SOURCE_USASPENDING_FILES_URL="https://files.example.gov/",
        DATA_SOURCE_USASPENDING_API_URL="https://api.example.gov/",
        DATA_SOURCE_FISCALDATA_API_URL="https://fiscal.example.gov/",
        SPARK_MASTER="local[1]",
        SPARK_DRIVER_MEMORY="1g",
        SPARK_SHUFFLE_PARTITIONS=1,
    )
    session = deequ_session(settings)
    yield session
    stop_session(session)


def frame(spark: SparkSession, rows: list[tuple[Any, ...]]) -> DataFrame:
    return spark.createDataFrame(rows, SCHEMA)


def test_fiscal_year_runs_october_to_september():
    assert fiscal_year_bounds(2025) == (date(2024, 10, 1), date(2025, 9, 30))


def test_clean_data_passes_every_error_check(spark, tmp_path):
    rows = [good_row("T1"), good_row("T2"), good_row("T3")]
    results = run_checks(spark, frame(spark, rows), [2025], tmp_path / "metrics.json")
    assert all(r.status == "Success" for r in results if r.check_level == "Error")
    assert (tmp_path / "metrics.json").exists()


@pytest.mark.parametrize(
    ("bad_row", "constraint"),
    [
        (good_row("T1"), "Uniqueness"),
        (good_row("T9", recipient_uei=None), "Completeness"),
        (good_row("T9", action_date=date(2025, 10, 1)), "within the fiscal years"),
        (good_row("T9", action_date_fiscal_year=2019), "configured years"),
        (good_row("T9", federal_action_obligation=Decimal("2000000000000.00")), "sane bounds"),
    ],
)
def test_error_level_violations_stop_the_build(spark, tmp_path, bad_row, constraint):
    rows = [good_row("T1"), good_row("T2"), bad_row]
    with pytest.raises(QualityError, match=constraint):
        run_checks(spark, frame(spark, rows), [2025], tmp_path / "metrics.json")


def test_personal_data_columns_stop_the_build(spark, tmp_path):
    leaked = frame(spark, [good_row("T1")]).withColumnRenamed(
        "awarding_agency_name", "recipient_phone_number"
    )
    with pytest.raises(QualityError, match="personal data"):
        run_checks(spark, leaked, [2025], tmp_path / "metrics.json")


def test_warning_level_findings_are_reported_without_failing(spark, tmp_path):
    rows = [good_row(f"T{i}", recipient_uei="not-a-uei") for i in range(5)]
    results = run_checks(spark, frame(spark, rows), [2025], tmp_path / "metrics.json")
    warnings = [r for r in results if r.check_level == "Warning" and r.status != "Success"]
    assert warnings
