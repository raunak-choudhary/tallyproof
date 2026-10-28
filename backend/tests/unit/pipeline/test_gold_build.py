import gzip
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pyspark.sql.types import StructField, StructType

from tallyproof_pipeline.gold import build_gold, read_events
from tallyproof_pipeline.overlay import Anomaly
from tallyproof_pipeline.silver import SILVER_COLUMNS

pytestmark = pytest.mark.spark


def silver_rows() -> list[dict[str, object]]:
    rows = []
    for i in range(30):
        row = dict.fromkeys(SILVER_COLUMNS)
        row.update(
            contract_transaction_unique_key=f"T{i:03d}",
            contract_award_unique_key=f"CONT_AWD_A{i % 6}",
            award_id_piid=f"PIID{i % 6}",
            modification_number="0" if i % 3 == 0 else f"P{i:05d}",
            federal_action_obligation=Decimal("100.00") * (i + 1),
            action_date=date(2025, 1, 1 + i % 28),
            action_date_fiscal_year=2025,
            last_modified_date=datetime(2025, 2, 1, 12, 0),
            awarding_agency_name="Department of Energy",
            recipient_uei=f"UEI{i % 4:09d}" if i != 5 else "",
        )
        rows.append(row)
    return rows


# Silver's real schema, so Spark never has to guess types from mostly-empty rows.
SCHEMA = StructType([StructField(name, data_type) for name, data_type in SILVER_COLUMNS.items()])


def test_build_gold_writes_events_labels_and_a_report(spark, spark_settings):
    settings = spark_settings
    rows = [tuple(row[name] for name in SILVER_COLUMNS) for row in silver_rows()]
    report = build_gold(settings, spark.createDataFrame(rows, SCHEMA))
    events = list(read_events(settings.gold_dir / "events.jsonl.gz"))
    labels = (settings.gold_dir / "labels.jsonl").read_text().splitlines()
    assert report.real_events + report.rows_rejected == 20
    assert report.rows_rejected == 1  # the row with an empty recipient UEI
    assert len(events) == report.real_events + report.injected_events
    assert len(labels) == 2 * len(Anomaly)
    with gzip.open(settings.gold_dir / "invalid_records.jsonl.gz", "rt") as handle:
        assert len(handle.read().splitlines()) == report.invalid_records == 2
    saved = json.loads((settings.gold_dir / "report.json").read_text())
    assert saved["real_events"] == report.real_events
    assert not (settings.gold_dir / "_base.jsonl.gz").exists()


def test_gold_events_are_in_arrival_order_with_anomalies_merged_in(spark, spark_settings):
    rows = [tuple(row[name] for name in SILVER_COLUMNS) for row in silver_rows()]
    build_gold(spark_settings, spark.createDataFrame(rows, SCHEMA))
    events = list(read_events(spark_settings.gold_dir / "events.jsonl.gz"))
    keys = [(e.emitted_at, e.idempotency_key) for e in events]
    assert keys == sorted(keys)


def test_slice_larger_than_silver_takes_everything(spark, spark_settings):
    from tallyproof_pipeline.gold import replay_slice

    rows = [tuple(row[name] for name in SILVER_COLUMNS) for row in silver_rows()]
    assert replay_slice(spark.createDataFrame(rows, SCHEMA), 1000).count() == 30


def test_slice_cuts_inside_a_day_deterministically(spark):
    from tallyproof_pipeline.gold import replay_slice

    rows = [tuple(row[name] for name in SILVER_COLUMNS) for row in silver_rows()]
    first = [
        r["contract_transaction_unique_key"]
        for r in replay_slice(spark.createDataFrame(rows, SCHEMA), 3).collect()
    ]
    second = [
        r["contract_transaction_unique_key"]
        for r in replay_slice(spark.createDataFrame(rows, SCHEMA), 3).collect()
    ]
    assert first == second
    assert len(first) == 3


def test_reservoir_pool_samples_across_the_whole_slice(spark, spark_settings, monkeypatch):
    from tallyproof_pipeline import gold

    monkeypatch.setattr(gold, "POOL_SIZE", 2)
    rows = [tuple(row[name] for name in SILVER_COLUMNS) for row in silver_rows()]
    report = gold.build_gold(spark_settings, spark.createDataFrame(rows, SCHEMA))
    assert report.injected_events > 0


def test_rows_out_of_arrival_order_stop_the_build(spark, spark_settings, monkeypatch):
    from pyspark.sql import functions as F  # noqa: N812

    from tallyproof_pipeline import gold

    original = gold.replay_slice
    monkeypatch.setattr(
        gold,
        "replay_slice",
        lambda silver, limit: original(silver, limit).orderBy(F.col("_emitted").desc()),
    )
    rows = [tuple(row[name] for name in SILVER_COLUMNS) for row in silver_rows()]
    with pytest.raises(gold.GoldOrderError, match="out of order"):
        gold.build_gold(spark_settings, spark.createDataFrame(rows, SCHEMA))


def test_outlays_for_awards_in_the_slice_are_merged_in_arrival_order(
    spark, spark_settings, tmp_path
):
    from tallyproof_core.events import EventType, OutlayReported
    from tallyproof_pipeline.gold import GoldOrderError, build_gold, slice_outlays, stream_outlays

    settings = spark_settings.model_copy(update={"data_dir": tmp_path})
    outlays = [
        # (award, account, year, period, cumulative, change, reported)
        (
            "CONT_AWD_A1",
            "097-0100",
            2025,
            4,
            Decimal("300.00"),
            Decimal("300.00"),
            datetime(2025, 2, 10, 8, 0),
        ),
        (
            "CONT_AWD_A1",
            "097-0100",
            2025,
            5,
            Decimal("450.00"),
            Decimal("150.00"),
            None,
        ),  # stamped at period end
        (
            "CONT_AWD_ZZ",
            "097-0100",
            2025,
            4,
            Decimal("50.00"),
            Decimal("50.00"),
            datetime(2025, 2, 10, 8, 0),
        ),
    ]
    spark.createDataFrame(
        outlays,
        "award_key string, treasury_account string, fiscal_year int, fiscal_period int, "
        "cumulative_outlay decimal(19,2), period_outlay decimal(19,2), reported_at timestamp_ntz",
    ).write.parquet(str(settings.silver_dir / "outlays" / "source=x"))

    rows = [tuple(row[name] for name in SILVER_COLUMNS) for row in silver_rows()]
    report = build_gold(settings, spark.createDataFrame(rows, SCHEMA))
    events = list(read_events(settings.gold_dir / "events.jsonl.gz"))
    real_outlays = [e for e in events if e.idempotency_key.startswith("usaspending:outlay:")]
    assert report.outlay_events == len(real_outlays) == 2  # CONT_AWD_ZZ isn't in the slice
    first, second = real_outlays
    assert first.payload.model_dump(mode="json")["period_outlay"] == "300.00"
    assert first.account_id == next(
        e.account_id for e in events if e.idempotency_key == "usaspending:T001"
    )
    assert second.emitted_at == datetime(2025, 2, 28, tzinfo=UTC)
    keys = [(e.emitted_at, e.idempotency_key) for e in events]
    assert keys == sorted(keys)
    injected = [
        e.payload for e in events if isinstance(e.payload, OutlayReported) and e not in real_outlays
    ]
    assert injected
    assert {p.treasury_account for p in injected} == {"097-0100"}
    assert all(e.event_type is EventType.OUTLAY_REPORTED for e in real_outlays)

    sorted_rows = slice_outlays(spark, settings, {"CONT_AWD_A1": "UEI000000001"})
    assert sorted_rows is not None
    backwards = sorted_rows.orderBy(sorted_rows["_emitted"].desc())
    with pytest.raises(GoldOrderError, match="out of order"):
        list(stream_outlays(backwards, {"CONT_AWD_A1": "UEI000000001"}, seed=1))
