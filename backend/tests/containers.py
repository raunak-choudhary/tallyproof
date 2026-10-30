"""Throwaway Postgres and Redpanda containers, shared by every test that asks for one.

Postgres gets the same role script and the same migrations as the local stack and
production, so tests check the real grants and triggers. The fixtures live here,
loaded once from ``tests/conftest.py``, so integration tests and the module suites
that need a database share one container and one migration run per session.
Nothing starts unless a test requests a fixture.
"""

import secrets
from collections.abc import Iterator
from dataclasses import dataclass

import psycopg
import pytest
from django.core.management import call_command
from django.db import connections
from pytest_django import DjangoDbBlocker
from testcontainers.community.kafka import RedpandaContainer
from testcontainers.community.postgres import PostgresContainer

from tallyproof_pipeline.settings import REPO_ROOT

POSTGRES_IMAGE = "pgvector/pgvector:0.8.7-pg16-trixie"
REDPANDA_IMAGE = "docker.redpanda.com/redpandadata/redpanda:v26.2.6"
ROLE_SCRIPT = REPO_ROOT / "infra" / "postgres" / "create-roles.sql"
ROLES = ("owner", "app", "analyst")


@dataclass(frozen=True)
class Database:
    """Connection strings for each role on the test database."""

    host: str
    port: int
    passwords: dict[str, str]

    def url(self, role: str) -> str:
        user = "postgres" if role == "superuser" else f"tallyproof_{role}"
        return f"postgresql://{user}:{self.passwords[role]}@{self.host}:{self.port}/tallyproof"

    def connect(self, role: str) -> psycopg.Connection:
        return psycopg.connect(self.url(role), autocommit=True)


@pytest.fixture(scope="session")
def database() -> Iterator[Database]:
    passwords = {role: secrets.token_urlsafe(16) for role in (*ROLES, "superuser")}
    container = PostgresContainer(
        POSTGRES_IMAGE,
        username="postgres",
        password=passwords["superuser"],
        dbname="tallyproof",
        driver=None,
    ).with_volume_mapping(str(ROLE_SCRIPT), "/infra/create-roles.sql", "ro")
    with container:
        variables = [f"-v{role}_password={passwords[role]}" for role in ROLES]
        result = container.exec(
            [
                "psql",
                "-U",
                "postgres",
                "-d",
                "tallyproof",
                *variables,
                "-f",
                "/infra/create-roles.sql",
            ]
        )
        assert result.exit_code == 0, result.output.decode()
        yield Database(
            container.get_container_host_ip(), int(container.get_exposed_port(5432)), passwords
        )


@pytest.fixture(scope="session")
def django_db_setup(database: Database, django_db_blocker: DjangoDbBlocker) -> None:
    """Migrate as the owner, then connect as the app role, exactly like the services.

    Tests that go through Django therefore run with the app role's grants, so a
    missing grant fails a test instead of passing silently as the owner.
    """
    settings = connections["default"].settings_dict
    settings.update(
        NAME="tallyproof",
        USER="tallyproof_owner",
        PASSWORD=database.passwords["owner"],
        HOST=database.host,
        PORT=str(database.port),
    )
    with django_db_blocker.unblock():
        call_command("migrate", verbosity=0)
        connections["default"].close()
    settings.update(USER="tallyproof_app", PASSWORD=database.passwords["app"])


@pytest.fixture
def migrated(django_db_setup: None, database: Database) -> Database:
    """The migrated test database. Tests use their own role connections."""
    with database.connect("superuser") as conn:
        for table in ("ledger_totals", "ledger_event"):
            conn.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
            conn.execute(f"DELETE FROM {table}")  # noqa: S608 - two fixed table names
            conn.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")
        conn.execute("UPDATE merkle_log_head SET next_leaf_index = 0")
    return database


@pytest.fixture(scope="session")
def redpanda() -> Iterator[RedpandaContainer]:
    """One Redpanda broker and schema registry, shared by every test that needs one."""
    with RedpandaContainer(REDPANDA_IMAGE) as container:
        yield container
