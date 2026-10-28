"""Profile silver: null rates per column and the shape of the obligation amounts.

The data profile in ``docs/data-profile.md`` is written from this report, so its
numbers can be reproduced with ``make data-profile``. Everything is computed in
one pass of aggregates plus approximate quantiles, so it runs in about a minute on
both fiscal years.

Usage::

    python -m tallyproof_pipeline.profile
"""

import json
import logging
from dataclasses import asdict, dataclass
from decimal import Decimal

from pyspark.sql import DataFrame
from pyspark.sql import functions as F  # noqa: N812 - conventional alias

from tallyproof_pipeline.settings import PipelineSettings, get_settings
from tallyproof_pipeline.silver import SILVER_COLUMNS, spark_session

log = logging.getLogger(__name__)

QUANTILES = (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99)
QUANTILE_ERROR = 0.001
TOP = 10


@dataclass
class Profile:
    """Null rates, amount distribution, and the most common categories in silver."""

    rows: int
    rows_by_fiscal_year: dict[str, int]
    null_rate: dict[str, float]
    amounts: dict[str, str]
    amount_quantiles: dict[str, str]
    top_awarding_agencies: list[tuple[str, int]]
    top_action_types: list[tuple[str, int]]


def _money(value: object) -> str:
    return "" if value is None else f"{Decimal(str(value)):.2f}"


def _top(silver: DataFrame, column: str) -> list[tuple[str, int]]:
    rows = (
        silver.groupBy(column)
        .count()
        .orderBy(F.col("count").desc(), F.col(column))
        .limit(TOP)
        .collect()
    )
    return [
        (str(row[column]) if row[column] is not None else "(missing)", row["count"]) for row in rows
    ]


def profile(silver: DataFrame) -> Profile:
    """Compute the profile of a silver contracts table."""
    amount = F.col("federal_action_obligation")
    totals = silver.agg(
        F.count(F.lit(1)).alias("rows"),
        *(F.sum(F.col(c).isNull().cast("long")).alias(f"null_{c}") for c in SILVER_COLUMNS),
        F.sum((amount > 0).cast("long")).alias("positive"),
        F.sum((amount < 0).cast("long")).alias("negative"),
        F.sum((amount == 0).cast("long")).alias("zero"),
        F.sum(F.when(amount > 0, amount)).alias("positive_total"),
        F.sum(F.when(amount < 0, amount)).alias("negative_total"),
        F.min(amount).alias("min"),
        F.max(amount).alias("max"),
    ).first()
    assert totals is not None  # noqa: S101 - an aggregate always returns one row
    rows = int(totals["rows"])
    quantiles = silver.select(amount.cast("double").alias("amount")).approxQuantile(
        "amount", list(QUANTILES), QUANTILE_ERROR
    )
    by_year = silver.groupBy("action_date_fiscal_year").count().collect()
    return Profile(
        rows=rows,
        rows_by_fiscal_year={str(r["action_date_fiscal_year"]): r["count"] for r in by_year},
        null_rate={
            c: round(int(totals[f"null_{c}"]) / rows, 6) if rows else 0.0 for c in SILVER_COLUMNS
        },
        amounts={
            "positive_rows": str(totals["positive"]),
            "negative_rows": str(totals["negative"]),
            "zero_rows": str(totals["zero"]),
            "positive_total": _money(totals["positive_total"]),
            "negative_total": _money(totals["negative_total"]),
            "min": _money(totals["min"]),
            "max": _money(totals["max"]),
        },
        amount_quantiles={
            f"p{round(q * 100)}": _money(v) for q, v in zip(QUANTILES, quantiles, strict=True)
        },
        top_awarding_agencies=_top(silver, "awarding_agency_name"),
        top_action_types=_top(silver, "action_type"),
    )


def main() -> None:  # pragma: no cover - thin command-line wrapper
    """Profile silver and write the report next to the other silver reports."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings: PipelineSettings = get_settings()
    spark = spark_session(settings)
    try:
        result = profile(spark.read.parquet(str(settings.silver_dir / "contracts")))
    finally:
        spark.stop()
    out = settings.silver_dir / "_reports" / "profile.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(result), indent=2, sort_keys=True) + "\n")
    print(f"profiled {result.rows:,} rows into {out}")


if __name__ == "__main__":  # pragma: no cover
    main()
