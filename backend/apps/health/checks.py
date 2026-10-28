"""Dependency checks used by the readiness endpoint."""

from collections.abc import Callable

from confluent_kafka.admin import AdminClient
from django.db import connection

from config.env import app_settings

Check = Callable[[], None]
"""A check raises on failure and returns nothing on success."""


def database() -> None:
    """Run a trivial query against the default database."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")


def broker() -> None:
    """Ask the Kafka-compatible broker for its metadata."""
    client = AdminClient({"bootstrap.servers": app_settings().kafka_bootstrap_servers})
    client.list_topics(timeout=2)


CHECKS: dict[str, Check] = {"database": database, "broker": broker}
"""Every dependency /readyz checks, by name."""
