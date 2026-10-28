"""Data quality checks on silver with Amazon Deequ.

Deequ runs declarative constraints inside Spark. Error-level constraints stop the
build: if a key field is missing, a transaction key repeats, or a date falls
outside its fiscal year, nothing downstream should trust the data. Warning-level
constraints are reported but do not fail the build.

Results are written to ``silver/_quality/`` as a readable JSON report, and every
run's metrics are appended to a Deequ metrics repository so quality can be
compared across runs.

Usage::

    python -m tallyproof_pipeline.quality
"""

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pydeequ
from pydeequ.checks import Check, CheckLevel
from pydeequ.repository import FileSystemMetricsRepository, ResultKey
from pydeequ.verification import VerificationResult, VerificationSuite
from pyspark.sql import DataFrame, SparkSession

from tallyproof_pipeline.settings import PipelineSettings, get_settings
from tallyproof_pipeline.silver import PII_COLUMNS, spark_session

log = logging.getLogger(__name__)

UEI_PATTERN = r"^[A-Z0-9]{12}$"
MAX_ABS_OBLIGATION = 1_000_000_000_000  # a trillion dollars: anything larger is a parse error


class QualityError(RuntimeError):
    """Raised when an error-level data quality constraint fails."""


@dataclass(frozen=True)
class ConstraintResult:
    """The outcome of one Deequ constraint."""

    check_level: str
    constraint: str
    status: str
    message: str


def fiscal_year_bounds(fiscal_year: int) -> tuple[date, date]:
    """Return the first and last day of a U.S. federal fiscal year (October to September)."""
    return date(fiscal_year - 1, 10, 1), date(fiscal_year, 9, 30)


def error_checks(spark: SparkSession, fiscal_years: list[int]) -> Check:
    """Constraints that must hold, or the build stops."""
    first = fiscal_year_bounds(min(fiscal_years))[0]
    last = fiscal_year_bounds(max(fiscal_years))[1]
    return (
        Check(spark, CheckLevel.Error, "silver contracts: must hold")
        .isComplete("contract_transaction_unique_key")
        .isUnique("contract_transaction_unique_key")
        .isComplete("contract_award_unique_key")
        .isComplete("recipient_uei")
        .isComplete("action_date")
        .satisfies(
            f"action_date_fiscal_year IN ({', '.join(str(year) for year in fiscal_years)})",
            "fiscal year is one of the configured years",
            lambda share: share == 1.0,
        )
        .satisfies(
            f"action_date >= DATE'{first}' AND action_date <= DATE'{last}'",
            "action_date within the fiscal years",
            lambda share: share == 1.0,
        )
        .satisfies(
            "federal_action_obligation IS NULL"
            f" OR abs(federal_action_obligation) < {MAX_ABS_OBLIGATION}",
            "obligation within sane bounds",
            lambda share: share == 1.0,
        )
    )


def warning_checks(spark: SparkSession) -> Check:
    """Constraints worth reporting that should not stop the build."""
    return (
        Check(spark, CheckLevel.Warning, "silver contracts: expected")
        .hasCompleteness("federal_action_obligation", lambda share: share >= 0.99)
        .hasPattern("recipient_uei", UEI_PATTERN, lambda share: share >= 0.99)
        .hasCompleteness("awarding_agency_name", lambda share: share >= 0.99)
    )


def run_checks(
    spark: SparkSession, silver: DataFrame, fiscal_years: list[int], repository_path: Path
) -> list[ConstraintResult]:
    """Run every check on a silver DataFrame and record the metrics.

    Raises:
        QualityError: If personal data columns are present or an error-level
            constraint fails.
    """
    leaked = PII_COLUMNS & set(silver.columns)
    if leaked:
        raise QualityError(f"personal data columns reached silver: {sorted(leaked)}")

    repository = FileSystemMetricsRepository(spark, str(repository_path))
    result_key = ResultKey(spark, ResultKey.current_milli_time(), {"dataset": "silver.contracts"})
    result = (
        VerificationSuite(spark)
        .onData(silver)
        .addCheck(error_checks(spark, fiscal_years))
        .addCheck(warning_checks(spark))
        .useRepository(repository)
        .saveOrAppendResult(result_key)
        .run()
    )
    rows = VerificationResult.checkResultsAsDataFrame(spark, result).collect()
    results = [
        ConstraintResult(
            check_level=row["check_level"],
            constraint=row["constraint"],
            status=row["constraint_status"],
            message=row["constraint_message"] or "",
        )
        for row in rows
    ]
    failed = [r for r in results if r.check_level == "Error" and r.status != "Success"]
    if failed:
        details = "; ".join(f"{r.constraint}: {r.message}" for r in failed)
        raise QualityError(f"{len(failed)} error-level constraint(s) failed: {details}")
    return results


def deequ_session(settings: PipelineSettings) -> SparkSession:
    """Start Spark with the Deequ library on its classpath."""
    return spark_session(
        settings,
        extra={
            "spark.jars.packages": pydeequ.deequ_maven_coord,
            "spark.jars.excludes": pydeequ.f2j_maven_coord,
        },
    )


def stop_session(spark: SparkSession) -> None:
    """Stop a Deequ Spark session, closing the py4j callback server PyDeequ opens."""
    gateway = spark.sparkContext._gateway
    if gateway is not None:
        gateway.shutdown_callback_server()
    spark.stop()


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Check all silver contracts and write the quality report."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    spark = deequ_session(settings)
    try:
        silver = spark.read.parquet(str(settings.silver_dir / "contracts"))
        out = settings.silver_dir / "_quality"
        out.mkdir(parents=True, exist_ok=True)
        results = run_checks(spark, silver, settings.fiscal_years, out / "metrics.json")
        (out / "report.json").write_text(json.dumps([r.__dict__ for r in results], indent=2) + "\n")
        for r in results:
            print(f"[{r.check_level}] {r.status:<8} {r.constraint}")
    finally:
        stop_session(spark)


if __name__ == "__main__":  # pragma: no cover
    main()
