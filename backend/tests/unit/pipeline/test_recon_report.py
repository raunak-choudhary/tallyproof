"""The reconciliation report counts a label as caught when its event is in a break."""

from typing import Any

from tallyproof_pipeline.recon_report import score


def test_caught_and_missed_labels_are_counted_per_anomaly() -> None:
    labels: list[dict[str, Any]] = [
        {"anomaly": "recipient_burst", "event_id": "evt_a"},
        {"anomaly": "recipient_burst", "event_id": "evt_b"},
        {"anomaly": "orphan_outlay", "event_id": "evt_c"},
        {"anomaly": "schema_invalid", "event_id": None},
    ]
    found = {"recipient_burst": {"evt_a", "evt_z"}, "orphan_outlay": {"evt_c"}}
    result = score(labels, found)
    assert result["recipient_burst"] == {"labelled": 2, "caught": 1}
    assert result["orphan_outlay"] == {"labelled": 1, "caught": 1}
    assert result["late_arrival"] == {"labelled": 0, "caught": 0}
