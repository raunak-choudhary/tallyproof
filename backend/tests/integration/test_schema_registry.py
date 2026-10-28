import json

import pytest
from testcontainers.community.kafka import RedpandaContainer

from apps.ingestion.schemas import SCHEMA_FILE, is_compatible, register


@pytest.fixture(scope="module")
def registry(redpanda: RedpandaContainer) -> str:
    return redpanda.get_schema_registry_address()


def test_backward_compatible_changes_are_accepted_and_breaking_ones_refused(registry):
    subject = "fin.events.raw.v1-value"
    committed = SCHEMA_FILE.read_text()
    assert register(registry, subject, committed) > 0
    assert is_compatible(registry, subject, committed)

    schema = json.loads(committed)
    optional = {**schema, "properties": {**schema["properties"], "trace_note": {"type": "string"}}}
    assert is_compatible(registry, subject, json.dumps(optional))

    breaking = {**schema, "required": [*schema["required"], "trace_note"]}
    breaking["properties"] = optional["properties"]
    assert not is_compatible(registry, subject, json.dumps(breaking))
