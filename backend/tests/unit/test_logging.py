import json
import logging

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
