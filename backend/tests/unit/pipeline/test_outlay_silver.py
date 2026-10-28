import csv
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tallyproof_pipeline.outlay_silver import (
    SOURCE_COLUMNS,
    build_outlay_silver,
    derive,
    period_end,
    reported_at,
    stage,
)
from tallyproof_pipeline.silver import read_csv

pytestmark = pytest.mark.spark

HEADER = [*SOURCE_COLUMNS, "object_class_code", "recipient_name"]


def row(award: str, account: str, period: str, outlay: str, modified: str = "") -> dict[str, str]:
    return {
        "award_unique_key": award,
        "treasury_account_symbol": account,
        "submission_period": period,
        "gross_outlay_amount_FYB_to_period_end": outlay,
        "last_modified_date": modified or "2023-11-10 14:00:00+00",
        "object_class_code": "25.2",
        "recipient_name": "ACME LABS INC",
    }


A, B = "CONT_AWD_A_9700_-NONE-_-NONE-", "CONT_AWD_B_9700_-NONE-_-NONE-"
FIRST = [
    row(A, "097-0100", "FY2024P01", "60.00"),
    row(A, "097-0100", "FY2024P01", "40.00"),  # second object class, same period
    row(A, "097-0100", "FY2024P02", "250.00", "2023-12-12 09:30:00+00"),
    row(B, "097-0100", "FY2024P01", "500.00"),
    row("ASST_NON_X_1", "075-0350", "FY2024P01", "999.00"),  # a grant, not a contract
]
SECOND = [
    row(A, "097-0100", "FY2024P03", "250.00"),  # no change: nothing paid
    row(A, "021-2020", "FY2024Q1", "30.00"),  # a quarterly reporter
    row(B, "097-0100", "FY2024P02", "400.00"),  # went down: quarantined
    row("CONT_AWD_C", "097-0100", "FY2024X", "10.00"),
    row("CONT_AWD_D", "097-0100", "FY2024P01", ""),
    row("CONT_AWD_E", "", "FY2024P01", "5.00"),
]


def write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture(scope="module")
def derived(spark, tmp_path_factory):
    path = write_csv(tmp_path_factory.mktemp("outlays") / "all.csv", FIRST + SECOND)
    silver, quarantined, counts = derive(stage(read_csv(spark, path)))
    return silver.collect(), quarantined.collect(), counts


def test_periods_are_added_up_and_turned_into_payments(derived):
    silver, _, _ = derived
    payments = {
        (r["award_key"], r["treasury_account"], r["fiscal_period"]): (
            r["cumulative_outlay"],
            r["period_outlay"],
        )
        for r in silver
    }
    assert payments == {
        (A, "097-0100", 1): (Decimal("100.00"), Decimal("100.00")),
        (A, "097-0100", 2): (Decimal("250.00"), Decimal("150.00")),
        (A, "021-2020", 3): (Decimal("30.00"), Decimal("30.00")),
        (B, "097-0100", 1): (Decimal("500.00"), Decimal("500.00")),
    }


def test_the_latest_report_time_is_kept_as_utc_wall_clock(derived):
    silver, _, _ = derived
    by_period = {r["fiscal_period"]: r for r in silver if r["award_key"] == A}
    assert by_period[2]["reported_at"] == datetime(2023, 12, 12, 9, 30)


def test_unusable_rows_and_shrinking_outlays_are_quarantined_with_reasons(derived):
    _, quarantined, counts = derived
    assert sorted((r["award_key"], r["reason"]) for r in quarantined) == [
        (B, "negative_period_outlay"),
        ("CONT_AWD_C", "unparseable_submission_period"),
        ("CONT_AWD_D", "missing_outlay"),
        ("CONT_AWD_E", "missing_treasury_account"),
    ]
    assert counts["no_change"] == 1


def test_missing_source_columns_fail_loudly(spark):
    frame = spark.createDataFrame([("x",)], ["award_unique_key"])
    with pytest.raises(ValueError, match="missing expected columns"):
        stage(frame)


def test_an_award_split_across_csv_members_is_derived_as_one_history(spark, spark_settings):
    settings = spark_settings
    folder = settings.data_dir / "csv"
    folder.mkdir(exist_ok=True)
    archive = settings.data_dir / "FY2024P01-P03_All_TAS_AccountBreakdownByAward_x.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(write_csv(folder / "a.csv", FIRST), "FY2024_All_TAS_Contracts_x_01.csv")
        bundle.write(write_csv(folder / "b.csv", SECOND), "FY2024_All_TAS_Contracts_x_02.csv")
        # Grant rows live in their own files, which are never read.
        bundle.write(
            write_csv(folder / "c.csv", [row("CONT_AWD_G", "1-1", "FY2024P01", "9.00")]),
            "FY2024_All_TAS_Assistance_x_01.csv",
        )
    report = build_outlay_silver(spark, settings, archive)
    assert report.rows_read == len(FIRST) + len(SECOND)
    assert report.contract_rows == len(FIRST) + len(SECOND) - 1
    assert report.periods_written == 4
    assert not (settings.work_dir / "outlays" / archive.stem).exists()
    assert (settings.silver_dir / "_reports" / "outlays" / f"{archive.stem}.json").exists()


@pytest.mark.parametrize(
    ("year", "period", "expected"),
    [(2024, 1, date(2023, 10, 31)), (2024, 3, date(2023, 12, 31)), (2024, 5, date(2024, 2, 29))],
)
def test_period_end_follows_the_fiscal_calendar(year, period, expected):
    assert period_end(year, period) == expected


def test_report_time_falls_back_to_the_period_end():
    assert reported_at(None, 2024, 1) == datetime(2023, 10, 31, tzinfo=UTC)
    assert reported_at(datetime(2023, 11, 10, 14), 2024, 1) == datetime(
        2023, 11, 10, 14, tzinfo=UTC
    )


def test_an_archive_without_contract_files_is_refused(spark, spark_settings):
    archive = spark_settings.data_dir / "FY2024P01-P03_All_TAS_AccountBreakdownByAward_y.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("FY2024_All_TAS_Assistance_y_01.csv", "award_unique_key\n")
    with pytest.raises(ValueError, match="no contract CSV files"):
        build_outlay_silver(spark, spark_settings, archive)
