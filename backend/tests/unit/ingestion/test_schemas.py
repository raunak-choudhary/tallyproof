from apps.ingestion.schemas import SCHEMA_FILE, event_schema, schema_text


def test_the_committed_schema_matches_the_models():
    # If this fails, regenerate with `make schemas` and review the diff.
    assert SCHEMA_FILE.read_text() == schema_text()


def test_the_schema_is_draft_07_with_internal_references_only():
    schema = event_schema()
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert "$defs" not in schema_text()
    refs = [line for line in schema_text().splitlines() if '"$ref"' in line]
    assert refs
    assert all("#/definitions/" in line for line in refs)
