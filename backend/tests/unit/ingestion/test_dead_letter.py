import json

from apps.ingestion.dead_letter import envelope, original, validate_fixed
from tests.unit.pipeline.test_overlay import real_events


def test_the_original_bytes_survive_the_round_trip():
    raw = b'{"broken": true}'
    record = envelope(ValueError("x"), "fin.events.raw.v1", 2, 40, raw)
    assert original(record) == raw


def test_only_files_where_every_record_passes_can_be_replayed():
    good = real_events(1)[0].model_dump_json()
    broken = json.loads(good)
    broken["payload"]["amount"] = 12.5
    bad = validate_fixed([good, json.dumps(broken), "not json"])
    assert [number for number, _ in bad] == [2, 3]
    assert validate_fixed([good]) == []
