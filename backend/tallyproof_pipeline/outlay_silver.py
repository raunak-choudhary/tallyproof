"""Bronze to silver for outlays: what was paid on each contract, per period.

An award financial file has one row per award, Treasury account, program
activity, object class, and submission period, and its outlay column is
cumulative from the start of the fiscal year. This job keeps contract awards
only, adds the rows up to one cumulative figure per award, account, and period,
and derives each period's payment as the change from the previous period.

Rows that can't be used are quarantined with a reason, never dropped silently. A
negative change, a payment that shrank without a correction we can see, is
quarantined too, as ADR-0016 describes. A period with no change produces no row,
because nothing was paid.

Usage::

    python -m tallyproof_pipeline.outlay_silver
"""

import calendar
import json
import logging
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F  # noqa: N812 - conventional alias

from tallyproof_pipeline.outlays import SOURCE_GLOB
from tallyproof_pipeline.settings import PipelineSettings, get_settings
from tallyproof_pipeline.silver import MONEY, read_csv, spark_session

log = logging.getLogger(__name__)

SOURCE_COLUMNS = (
    "award_unique_key",
    "treasury_account_symbol",
    "submission_period",
    "gross_outlay_amount_FYB_to_period_end",
    "last_modified_date",
)
"""The award financial columns this job reads. Nothing about people is among them."""

CONTRACT_PREFIX = "CONT_AWD_"
KEYS = ("award_key", "treasury_account", "fiscal_year", "fiscal_period")


@dataclass
class OutlayReport:
    """What happened to one award financial file."""

    archive: str
    rows_read: int = 0
    contract_rows: int = 0
    periods_written: int = 0
    dropped: dict[str, int] = field(default_factory=dict)


def period_end(fiscal_year: int, fiscal_period: int) -> date:
    """The last day of a fiscal period. Period 1 is October of the previous year."""
    month = (fiscal_period + 8) % 12 + 1
    year = fiscal_year - 1 if month >= 10 else fiscal_year
    return date(year, month, calendar.monthrange(year, month)[1])


def reported_at(row_value: datetime | None, fiscal_year: int, fiscal_period: int) -> datetime:
    """When the agency reported the figure, falling back to the period's end."""
    if row_value is not None:
        return row_value if row_value.tzinfo else row_value.replace(tzinfo=UTC)
    end = period_end(fiscal_year, fiscal_period)
    return datetime(end.year, end.month, end.day, tzinfo=UTC)


def stage(raw: DataFrame) -> DataFrame:
    """Keep contract rows and the columns this job needs, typed but not yet cleaned."""
    missing = [c for c in SOURCE_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"source is missing expected columns: {missing}")
    period = F.trim(F.col("submission_period"))
    quarter = F.regexp_extract(period, r"Q([1-4])$", 1)
    month = F.regexp_extract(period, r"P(\d{2})$", 1)
    return raw.where(F.col("award_unique_key").startswith(CONTRACT_PREFIX)).select(
        F.trim(F.col("award_unique_key")).alias("award_key"),
        F.trim(F.col("treasury_account_symbol")).alias("treasury_account"),
        F.regexp_extract(period, r"^FY(\d{4})", 1).try_cast("int").alias("fiscal_year"),
        F.when(month != "", month.try_cast("int"))
        .when(quarter != "", quarter.try_cast("int") * 3)
        .alias("fiscal_period"),
        F.trim(F.col("gross_outlay_amount_FYB_to_period_end")).try_cast(MONEY).alias("cumulative"),
        F.to_timestamp_ntz(
            F.date_format(
                F.coalesce(
                    F.try_to_timestamp(F.col("last_modified_date"), F.lit("yyyy-MM-dd HH:mm:ssx")),
                    F.try_to_timestamp(F.col("last_modified_date"), F.lit("yyyy-MM-dd")),
                ),
                "yyyy-MM-dd HH:mm:ss",
            )
        ).alias("reported_at"),
    )


def derive(staged: DataFrame) -> tuple[DataFrame, DataFrame, dict[str, int]]:
    """Turn staged rows into one payment per award, account, and period.

    Returns:
        The silver rows, the quarantined rows (with a ``reason``), and the number of
        rows set aside for each reason.
    """
    reason = F.coalesce(
        F.when(F.col("treasury_account").isNull(), F.lit("missing_treasury_account")),
        F.when(F.col("fiscal_year").isNull(), F.lit("unparseable_submission_period")),
        F.when(
            F.col("fiscal_period").isNull() | ~F.col("fiscal_period").between(1, 12),
            F.lit("unparseable_submission_period"),
        ),
        F.when(F.col("cumulative").isNull(), F.lit("missing_outlay")),
    )
    checked = staged.withColumn("reason", reason)
    bad_rows = checked.where(F.col("reason").isNotNull())

    totals = (
        checked.where(F.col("reason").isNull())
        .groupBy(*KEYS)
        .agg(
            F.sum("cumulative").cast(MONEY).alias("cumulative_outlay"),
            F.max("reported_at").alias("reported_at"),
        )
    )
    history = Window.partitionBy("award_key", "treasury_account", "fiscal_year").orderBy(
        "fiscal_period"
    )
    changes = totals.withColumn(
        "period_outlay",
        (
            F.col("cumulative_outlay")
            - F.coalesce(F.lag("cumulative_outlay").over(history), F.lit(0).cast(MONEY))
        ).cast(MONEY),
    )
    negative = changes.where(F.col("period_outlay") < 0).withColumn(
        "reason", F.lit("negative_period_outlay")
    )
    silver = changes.where(F.col("period_outlay") > 0)

    counts = {"no_change": changes.where(F.col("period_outlay") == 0).count()}
    for row in bad_rows.groupBy("reason").count().collect():
        counts[row["reason"]] = row["count"]
    counts["negative_period_outlay"] = negative.count()
    quarantined = bad_rows.select(
        "award_key", "treasury_account", "fiscal_year", "fiscal_period", "reason"
    ).unionByName(
        negative.select("award_key", "treasury_account", "fiscal_year", "fiscal_period", "reason")
    )
    return silver, quarantined, {k: v for k, v in counts.items() if v}


def build_outlay_silver(
    spark: SparkSession, settings: PipelineSettings, archive: Path
) -> OutlayReport:
    """Stage every CSV in one archive, then derive per-period payments from all of them.

    The CSV members are extracted and staged one at a time, so the disk never holds
    the whole file uncompressed. Payments are derived only after every member is
    staged, because one award's periods can be spread across members.
    """
    work = settings.work_dir / "outlays" / archive.stem
    staged_dir = work / "staged"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    report = OutlayReport(archive=archive.name)
    with zipfile.ZipFile(archive) as bundle:
        members = sorted(n for n in bundle.namelist() if n.endswith(".csv"))
    for member in members:
        extracted = work / Path(member).name
        with (
            zipfile.ZipFile(archive) as bundle,
            bundle.open(member) as source,
            extracted.open("wb") as target,
        ):
            shutil.copyfileobj(source, target, length=1024 * 1024)
        try:
            raw = read_csv(spark, extracted)
            report.rows_read += raw.count()
            stage(raw).write.mode("append").parquet(str(staged_dir))
        finally:
            extracted.unlink(missing_ok=True)

    staged = spark.read.parquet(str(staged_dir))
    report.contract_rows = staged.count()
    silver, quarantined, report.dropped = derive(staged)
    out = settings.silver_dir / "outlays" / f"source={archive.stem}"
    silver.write.mode("overwrite").parquet(str(out))
    quarantined.write.mode("overwrite").parquet(
        str(settings.silver_dir / "quarantine_outlays" / f"source={archive.stem}")
    )
    report.periods_written = spark.read.parquet(str(out)).count()
    shutil.rmtree(work, ignore_errors=True)

    reports = settings.silver_dir / "_reports" / "outlays"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{archive.stem}.json").write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    )
    return report


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Build outlay silver for every downloaded award financial file."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    spark = spark_session(settings)
    try:
        for archive in sorted(settings.bronze_dir.glob(SOURCE_GLOB)):
            log.info("processing %s", archive.name)
            report = build_outlay_silver(spark, settings, archive)
            print(
                f"{archive.name}: read {report.rows_read:,}, contracts {report.contract_rows:,}, "
                f"periods {report.periods_written:,}, set aside {report.dropped}"
            )
    finally:
        spark.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
