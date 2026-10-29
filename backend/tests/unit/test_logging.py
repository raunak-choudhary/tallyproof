import json
import logging

import pytest
from django.test import Client

from config.logging import bind_correlation_id, configure


def test_logs_are_json_lines_carrying_the_correlation_id(capsys):
    configure()
    bind_correlation_id("evt-trace-1")
    logging.getLogger("tallyproof.test").info("appended %s", "evt_1")
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["correlation_id"] == "evt-trace-1"
    assert line["event"] == "appended evt_1"
    assert line["level"] == "info"


def test_the_api_echoes_safe_correlation_ids_and_replaces_unsafe_ones():
    client = Client(HTTP_HOST="localhost")
    given = client.get("/healthz", HTTP_X_CORRELATION_ID="trace-42")
    assert given["X-Correlation-ID"] == "trace-42"
    injected = client.get("/healthz", HTTP_X_CORRELATION_ID="bad\nline")
    assert injected["X-Correlation-ID"].startswith("req-")


def last_line(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    line: dict[str, object] = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return line


def test_secrets_in_fields_and_connection_strings_are_redacted(capsys):
    configure()
    log = logging.getLogger("tallyproof.test")
    log.info("connecting to postgresql://tallyproof_app:s3cret-pw@127.0.0.1:15432/tallyproof")
    line = last_line(capsys)
    assert "s3cret-pw" not in json.dumps(line)
    assert (
        line["event"]
        == "connecting to postgresql://tallyproof_app:[redacted]@127.0.0.1:15432/tallyproof"
    )

    import structlog

    structlog.get_logger("tallyproof.test").info(
        "calling the model",
        api_key="sk-ant-123",
        password="hunter2",  # noqa: S106 - a fake secret the test expects to be hidden
        tree_size=42,
    )
    line = last_line(capsys)
    assert line["api_key"] == "[redacted]"
    assert line["password"] == "[redacted]"  # noqa: S105 - the masked value, not a secret
    assert line["tree_size"] == 42


def test_level_and_format_come_from_settings(capsys):
    configure(level="WARNING", fmt="console")
    log = logging.getLogger("tallyproof.test")
    log.info("hidden below the level")
    log.warning("shown")
    out = capsys.readouterr().out
    assert "hidden below the level" not in out
    assert "shown" in out
    assert not out.strip().startswith("{")  # console format, not JSON
    configure()


def test_secrets_inside_exception_text_are_redacted(capsys):
    configure()
    log = logging.getLogger("tallyproof.test")
    try:
        raise ConnectionError("cannot reach postgresql://tallyproof_app:s3cret-pw@db:5432/x")
    except ConnectionError:
        log.exception("database down")
    assert "s3cret-pw" not in capsys.readouterr().out
