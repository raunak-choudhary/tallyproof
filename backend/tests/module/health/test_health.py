import pytest
from django.test import Client

from apps.health import checks


@pytest.fixture
def client():
    return Client()


def test_healthz_answers_without_touching_dependencies(client, monkeypatch):
    monkeypatch.setattr(checks, "CHECKS", {"database": lambda: 1 / 0})
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_is_ready_when_every_check_passes(client, monkeypatch):
    monkeypatch.setattr(checks, "CHECKS", {"database": lambda: None, "broker": lambda: None})
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "broker": "ok"}}


def test_readyz_names_the_failing_dependency_without_leaking_details(client, monkeypatch):
    def broken() -> None:
        raise ConnectionError("password=hunter2 at db.internal:5432")

    monkeypatch.setattr(checks, "CHECKS", {"database": broken, "broker": lambda: None})
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "unavailable", "broker": "ok"}
    assert "hunter2" not in response.content.decode()


def test_openapi_schema_is_served(client):
    response = client.get("/api/v1/schema/")
    assert response.status_code == 200
    assert b"Tallyproof API" in response.content
