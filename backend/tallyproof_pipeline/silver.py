"""Bronze to silver: typed, deduplicated, personal-data-free contract transactions.

Each bronze archive holds several CSV files of about 2 GB. They are processed one
at a time so the job fits on a laptop with 8 GB of RAM: extract one CSV, clean
it with Spark, write Parquet, delete the CSV, move on.

Personal data is handled with an allowlist. Only the columns listed in
:data:`SILVER_COLUMNS` survive. Anything new the source adds later is dropped
automatically, and a test fails if any column in :data:`PII_COLUMNS` ever
reaches silver. Rows for sole proprietorships, whose recipient is an individual
person, are removed entirely.

Rows that cannot be typed are not silently dropped. They go to a quarantine
table with a reason code, and every removal is counted by reason.

Usage::

    python -m tallyproof_pipeline.silver
"""

import json
import logging
import shutil
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F  # noqa: N812 - conventional alias
from pyspark.sql.types import (
    DataType,
    DateType,
    DecimalType,
    IntegerType,
    StringType,
    TimestampNTZType,
)

from tallyproof_pipeline.settings import PipelineSettings, get_settings

log = logging.getLogger(__name__)

MONEY = DecimalType(19, 2)

SILVER_COLUMNS: dict[str, DataType] = {
    "contract_transaction_unique_key": StringType(),
    "contract_award_unique_key": StringType(),
    "award_id_piid": StringType(),
    "modification_number": StringType(),
    "parent_award_id_piid": StringType(),
    "federal_action_obligation": MONEY,
    "total_dollars_obligated": MONEY,
    "current_total_value_of_award": MONEY,
    "potential_total_value_of_award": MONEY,
    "action_date": DateType(),
    "action_date_fiscal_year": IntegerType(),
    "period_of_performance_start_date": DateType(),
    "period_of_performance_current_end_date": DateType(),
    "awarding_agency_code": StringType(),
    "awarding_agency_name": StringType(),
    "awarding_sub_agency_name": StringType(),
    "funding_agency_code": StringType(),
    "funding_agency_name": StringType(),
    "recipient_uei": StringType(),
    "recipient_name": StringType(),
    "recipient_parent_uei": StringType(),
    "recipient_parent_name": StringType(),
    "recipient_country_code": StringType(),
    "recipient_state_code": StringType(),
    "recipient_city_name": StringType(),
    "primary_place_of_performance_country_code": StringType(),
    "primary_place_of_performance_state_code": StringType(),
    "transaction_description": StringType(),
    "action_type_code": StringType(),
    "action_type": StringType(),
    "type_of_contract_pricing": StringType(),
    "product_or_service_code": StringType(),
    "naics_code": StringType(),
    "naics_description": StringType(),
    # Report times arrive as "2025-09-30 13:07:48+00" and are stored as UTC wall-clock
    # time without a zone. PySpark converts zoned timestamps into the local time zone
    # of whichever machine collects them, which would shift every event's time.
    "initial_report_date": TimestampNTZType(),
    "last_modified_date": TimestampNTZType(),
}
"""Every column kept in silver, with its type. Nothing else survives."""

PII_COLUMNS = frozenset(
    {
        *(f"highly_compensated_officer_{i}_name" for i in range(1, 6)),
        *(f"highly_compensated_officer_{i}_amount" for i in range(1, 6)),
        "recipient_address_line_1",
        "recipient_address_line_2",
        "recipient_phone_number",
        "recipient_fax_number",
        "recipient_zip_4_code",
        "primary_place_of_performance_zip_4",
    }
)
"""Columns that identify or describe people. Checked by tests, never kept."""

REQUIRED = ("contract_transaction_unique_key", "contract_award_unique_key", "recipient_uei")


@dataclass
class MemberReport:
    """What happened to one CSV member."""

    archive: str
    member: str
    rows_read: int = 0
    rows_written: int = 0
    dropped: dict[str, int] = field(default_factory=dict)


def spark_session(
    settings: PipelineSettings, extra: Mapping[str, str] | None = None
) -> SparkSession:
    """Start a local Spark session within the laptop resource budget.

    Args:
        settings: Supplies the master, driver memory, and shuffle partitions.
        extra: Additional Spark settings, for example the Deequ packages.
    """
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    builder = (
        SparkSession.builder.master(settings.spark_master)
        .appName("tallyproof")
        .config("spark.driver.memory", settings.spark_driver_memory)
        .config("spark.sql.shuffle.partitions", str(settings.spark_shuffle_partitions))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.local.dir", str(settings.work_dir / "spark"))
        .config("spark.ui.enabled", "false")
    )
    for key, value in (extra or {}).items():
        builder = builder.config(key, value)
    return builder.getOrCreate()


def _typed(column: str, data_type: DataType) -> Column:
    raw = F.trim(F.col(column))
    raw = F.when(raw == "", None).otherwise(raw)
    if isinstance(data_type, DecimalType):
        return raw.try_cast(data_type)
    if isinstance(data_type, DateType):
        return F.try_to_date(raw, "yyyy-MM-dd")
    if isinstance(data_type, TimestampNTZType):
        # Accept the source's "2025-09-30 13:07:48+00" and a plain date as a fallback,
        # then keep the UTC wall-clock time (the session time zone is UTC).
        instant = F.coalesce(
            F.try_to_timestamp(raw, F.lit("yyyy-MM-dd HH:mm:ssx")),
            F.try_to_timestamp(raw, F.lit("yyyy-MM-dd")),
        )
        return F.to_timestamp_ntz(F.date_format(instant, "yyyy-MM-dd HH:mm:ss"))
    if isinstance(data_type, IntegerType):
        return raw.try_cast(data_type)
    return raw


def transform(raw: DataFrame) -> tuple[DataFrame, DataFrame, dict[str, int]]:
    """Clean one raw CSV DataFrame.

    Returns:
        The silver rows, the quarantined rows (silver columns plus a ``reason``),
        and the number of rows removed for each reason.
    """
    missing = [c for c in SILVER_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"source is missing expected columns: {missing}")

    is_individual = F.lower(F.coalesce(F.col("sole_proprietorship"), F.lit("f"))) == F.lit("t")
    people = raw.where(is_individual)
    businesses = raw.where(~is_individual)

    typed = businesses.select(
        *(_typed(name, data_type).alias(name) for name, data_type in SILVER_COLUMNS.items()),
        *(
            F.trim(F.col(name)).alias(f"_raw_{name}")
            for name, data_type in SILVER_COLUMNS.items()
            if not isinstance(data_type, StringType)
        ),
    )

    reasons = [
        *(F.when(F.col(name).isNull(), F.lit(f"missing_{name}")) for name in REQUIRED),
        *(
            F.when(
                F.col(name).isNull()
                & F.col(f"_raw_{name}").isNotNull()
                & (F.col(f"_raw_{name}") != ""),
                F.lit(f"unparseable_{name}"),
            )
            for name, data_type in SILVER_COLUMNS.items()
            if not isinstance(data_type, StringType)
        ),
    ]
    with_reason = typed.withColumn("reason", F.coalesce(*reasons)).drop(
        *(c for c in typed.columns if c.startswith("_raw_"))
    )
    quarantined = with_reason.where(F.col("reason").isNotNull())
    valid = with_reason.where(F.col("reason").isNull()).drop("reason")
    silver = valid.dropDuplicates(["contract_transaction_unique_key"])

    counts = {
        "individual_recipient": people.count(),
        "duplicate_transaction": valid.count() - silver.count(),
    }
    for row in quarantined.groupBy("reason").count().collect():
        counts[row["reason"]] = row["count"]
    return silver, quarantined, {k: v for k, v in counts.items() if v}


def read_csv(spark: SparkSession, path: Path) -> DataFrame:
    """Read one USAspending CSV as strings; typing happens in :func:`transform`."""
    return (
        spark.read.option("header", True)
        .option("multiLine", True)  # descriptions can contain quoted newlines
        .option("escape", '"')
        .option("mode", "PERMISSIVE")
        .csv(str(path))
    )


def process_member(
    spark: SparkSession, settings: PipelineSettings, archive: Path, member: str
) -> MemberReport:
    """Extract one CSV member, clean it into silver Parquet, and delete the CSV."""
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    extracted = settings.work_dir / Path(member).name
    with (
        zipfile.ZipFile(archive) as bundle,
        bundle.open(member) as source,
        extracted.open("wb") as target,
    ):
        shutil.copyfileobj(source, target, length=1024 * 1024)
    try:
        raw = read_csv(spark, extracted)
        silver, quarantined, dropped = transform(raw)
        stem = Path(member).stem
        out = settings.silver_dir / "contracts" / f"source={archive.stem}" / f"member={stem}"
        silver.write.mode("overwrite").parquet(str(out))
        quarantine_out = (
            settings.silver_dir / "quarantine" / f"source={archive.stem}" / f"member={stem}"
        )
        quarantined.write.mode("overwrite").parquet(str(quarantine_out))
        report = MemberReport(
            archive=archive.name,
            member=member,
            rows_read=raw.count(),
            rows_written=spark.read.parquet(str(out)).count(),
            dropped=dropped,
        )
    finally:
        extracted.unlink(missing_ok=True)
    reports_dir = settings.silver_dir / "_reports" / archive.stem
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{Path(member).stem}.json").write_text(
        json.dumps(report.__dict__, indent=2, sort_keys=True) + "\n"
    )
    return report


def build_silver(settings: PipelineSettings) -> list[MemberReport]:  # pragma: no cover - full run
    """Process every CSV member of every downloaded archive."""
    spark = spark_session(settings)
    reports = []
    try:
        for archive in sorted(settings.bronze_dir.glob("*_Contracts_Full_*.zip")):
            with zipfile.ZipFile(archive) as bundle:
                members = sorted(n for n in bundle.namelist() if n.endswith(".csv"))
            for member in members:
                log.info("processing %s / %s", archive.name, member)
                reports.append(process_member(spark, settings, archive, member))
    finally:
        spark.stop()
    return reports


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Build silver for all downloaded archives and print a summary."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for report in build_silver(get_settings()):
        counts = f"read {report.rows_read:,}, wrote {report.rows_written:,}"
        print(f"{report.member}: {counts}, dropped {report.dropped}")


if __name__ == "__main__":  # pragma: no cover
    main()
