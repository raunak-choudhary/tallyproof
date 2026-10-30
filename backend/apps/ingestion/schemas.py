"""Event schemas in the Schema Registry, with backward compatibility enforced.

The JSON Schema for ``EventEnvelope`` is generated from the Pydantic models,
rewritten to draft-07 with internal references only (so it works in Redpanda's
registry and AWS Glue alike), and committed as ``schemas/events.v2.json``. A
test fails if the models change without regenerating that file, so every schema
change is a reviewed diff. ``schemas/events.v1.json`` stays committed as the
version it evolved from. Registration sets the subject to ``BACKWARD``: the
registry then refuses a new version that consumers of the old one can't read.
"""

import json
from pathlib import Path
from typing import Any

import requests

from tallyproof_core.events import EventEnvelope

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
SCHEMA_FILE = SCHEMA_DIR / "events.v2.json"
PREVIOUS_SCHEMA_FILE = SCHEMA_DIR / "events.v1.json"
CONTENT_TYPE = "application/vnd.schemaregistry.v1+json"


def _rewrite_refs(node: Any) -> Any:  # noqa: ANN401 - walks arbitrary JSON
    if isinstance(node, dict):
        return {
            key: (
                value.replace("#/$defs/", "#/definitions/")
                if key == "$ref"
                else _rewrite_refs(value)
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite_refs(item) for item in node]
    return node


def event_schema() -> dict[str, Any]:
    """The envelope's JSON Schema in draft-07 form."""
    schema = EventEnvelope.model_json_schema(mode="validation")
    definitions = schema.pop("$defs", {})
    schema = _rewrite_refs(schema)
    schema["definitions"] = _rewrite_refs(definitions)
    return {"$schema": "http://json-schema.org/draft-07/schema#", **schema}


def schema_text() -> str:
    """The schema exactly as committed."""
    return json.dumps(event_schema(), indent=2, sort_keys=True) + "\n"


def subject_for(topic: str) -> str:
    """The registry subject for a topic's message values."""
    return f"{topic}-value"


def register(registry: str, subject: str, schema: str, timeout: float = 10.0) -> int:
    """Enforce BACKWARD compatibility on the subject and register the schema. Returns its ID."""
    base = registry.rstrip("/")
    headers = {"Content-Type": CONTENT_TYPE}
    config = requests.put(
        f"{base}/config/{subject}",
        json={"compatibility": "BACKWARD"},
        headers=headers,
        timeout=timeout,
    )
    config.raise_for_status()
    response = requests.post(
        f"{base}/subjects/{subject}/versions",
        json={"schema": schema, "schemaType": "JSON"},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return int(response.json()["id"])


def is_compatible(registry: str, subject: str, schema: str, timeout: float = 10.0) -> bool:
    """Would the registry accept this schema as the subject's next version?"""
    response = requests.post(
        f"{registry.rstrip('/')}/compatibility/subjects/{subject}/versions/latest",
        json={"schema": schema, "schemaType": "JSON"},
        headers={"Content-Type": CONTENT_TYPE},
        timeout=timeout,
    )
    response.raise_for_status()
    return bool(response.json()["is_compatible"])
