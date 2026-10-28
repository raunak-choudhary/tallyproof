import csv
import zipfile
from decimal import Decimal

import pytest

from tallyproof_pipeline.silver import (
    PII_COLUMNS,
    SILVER_COLUMNS,
    member_done,
    process_member,
    read_csv,
    transform,
)

pytestmark = pytest.mark.spark

EXTRA = ["usaspending_permalink", "sole_proprietorship", "some_future_column"]
HEADER = [*SILVER_COLUMNS, *sorted(PII_COLUMNS), *EXTRA]


def row(key: str, **values: str) -> dict[str, str]:
    base = {name: "" for name in HEADER}
    base.update(
        contract_transaction_unique_key=key,
        contract_award_unique_key=f"CONT_AWD_{key}",
        award_id_piid=f"PIID{key}",
        modification_number="0",
        federal_action_obligation="1250.50",
        action_date="2025-03-14",
        action_date_fiscal_year="2025",
        # Real report times are timestamps with a UTC offset, not plain dates.
        initial_report_date="2025-03-15 13:07:48+00",
        last_modified_date="2025-03-20 04:28:07+00",
        awarding_agency_name="Department of Energy",
        recipient_uei="ZQGGHJH74DW7",
        recipient_name="ACME LABS INC",
        transaction_description="LABORATORY SERVICES",
        sole_proprietorship="f",
        highly_compensated_officer_1_name="Jane Example",
        highly_compensated_officer_1_amount="350000",
        recipient_address_line_1="1 Main St",
        recipient_phone_number="5555550100",
        some_future_column="anything",
    )
    base.update(values)
    return base


ROWS = [
    row("T1"),
    row("T2", sole_proprietorship="t", recipient_name="JOHN SMITH"),
    row("T1"),  # duplicate delivery of T1
    row("T3", federal_action_obligation="12x"),
    row("T4", recipient_uei=""),
    row("T5", transaction_description='SPLIT "QUOTED"\nACROSS LINES, WITH COMMA'),
    row("T6", action_date="2025-13-45"),
    row("T7", federal_action_obligation="-500.00"),
    row("T8", last_modified_date="not a time"),
]


@pytest.fixture(scope="module")
def csv_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("csv") / "FY2025_All_Contracts_Full_20261006_1.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(ROWS)
    return path


@pytest.fixture(scope="module")
def result(spark, csv_path):
    silver, quarantined, dropped = transform(read_csv(spark, csv_path))
    return silver.collect(), quarantined.collect(), dropped


def test_only_allowlisted_columns_survive(result):
    silver, _, _ = result
    assert set(silver[0].asDict()) == set(SILVER_COLUMNS)
    assert not PII_COLUMNS & set(silver[0].asDict())


def test_no_personal_data_values_survive_anywhere(result):
    silver, quarantined, _ = result
    text = " ".join(str(v) for r in [*silver, *quarantined] for v in r.asDict().values())
    for value in ("Jane Example", "350000", "1 Main St", "5555550100", "JOHN SMITH"):
        assert value not in text


def test_individual_recipients_and_duplicates_are_counted(result):
    _, _, dropped = result
    assert dropped["individual_recipient"] == 1
    assert dropped["duplicate_transaction"] == 1


def test_bad_rows_are_quarantined_with_reasons(result):
    _, quarantined, dropped = result
    reasons = {r["contract_transaction_unique_key"]: r["reason"] for r in quarantined}
    assert reasons == {
        "T3": "unparseable_federal_action_obligation",
        "T4": "missing_recipient_uei",
        "T6": "unparseable_action_date",
        "T8": "unparseable_last_modified_date",
    }
    assert dropped["missing_recipient_uei"] == 1


def test_amounts_are_exact_decimals_including_negative(result):
    silver, _, _ = result
    by_key = {r["contract_transaction_unique_key"]: r for r in silver}
    assert by_key["T1"]["federal_action_obligation"] == Decimal("1250.50")
    assert by_key["T7"]["federal_action_obligation"] == Decimal("-500.00")


def test_report_timestamps_keep_their_time_of_day_in_utc(result):
    silver, _, _ = result
    by_key = {r["contract_transaction_unique_key"]: r for r in silver}
    assert by_key["T1"]["last_modified_date"].isoformat() == "2025-03-20T04:28:07"


def test_quoted_newlines_and_commas_parse_into_one_field(result):
    silver, _, _ = result
    by_key = {r["contract_transaction_unique_key"]: r for r in silver}
    assert by_key["T5"]["transaction_description"] == 'SPLIT "QUOTED"\nACROSS LINES, WITH COMMA'
    assert set(by_key) == {"T1", "T5", "T7"}


def test_missing_expected_columns_fail_loudly(spark):
    frame = spark.createDataFrame([("x",)], ["contract_transaction_unique_key"])
    with pytest.raises(ValueError, match="missing expected columns"):
        transform(frame)


def test_process_member_writes_parquet_and_a_report_and_removes_the_csv(
    spark, spark_settings, csv_path
):
    settings = spark_settings
    archive = settings.data_dir / "FY2025_All_Contracts_Full_20261006.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(csv_path, csv_path.name)
    assert not member_done(settings, archive, csv_path.name)
    report = process_member(spark, settings, archive, csv_path.name)
    assert member_done(settings, archive, csv_path.name)
    assert report.rows_read == len(ROWS)
    assert report.rows_written == 3
    assert not (settings.work_dir / csv_path.name).exists()
    reports = list((settings.silver_dir / "_reports").rglob("*.json"))
    assert len(reports) == 1
