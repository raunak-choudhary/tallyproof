"""Helpers for reading the analyst views with exactly the analyst role's privileges."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.db import connection

from tests.integration.conftest import Database


@pytest.fixture
def as_analyst(migrated: Database) -> Iterator[None]:
    """Let the test's own connection read with exactly the analyst's privileges.

    The data the test appends is uncommitted, so only this connection can see it.
    Membership is granted for the test and taken away again afterwards.
    """
    with migrated.connect("superuser") as conn:
        conn.execute("GRANT tallyproof_analyst TO tallyproof_app")
    yield
    with migrated.connect("superuser") as conn:
        conn.execute("REVOKE tallyproof_analyst FROM tallyproof_app")


def query(sql: str, *params: Any) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        # SET ROLE doesn't apply the role's own settings, so pin its search path too.
        cursor.execute("SET LOCAL ROLE tallyproof_analyst")
        cursor.execute("SET LOCAL search_path = analyst")
        cursor.execute(sql, params)
        rows: list[tuple[Any, ...]] = cursor.fetchall()
        cursor.execute("RESET ROLE")
        cursor.execute("RESET search_path")
    return rows


class AsAnalyst:
    """An executor that runs SQL with the analyst role's privileges on the test connection."""

    def run(self, sql: str, params: Any) -> tuple[list[str], list[tuple[Any, ...]]]:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE tallyproof_analyst")
            cursor.execute("SET LOCAL search_path = analyst")
            cursor.execute(sql, list(params) if params else None)
            columns = [c.name for c in cursor.description or []]
            rows = [tuple(r) for r in cursor.fetchall()]
            cursor.execute("RESET ROLE")
            cursor.execute("RESET search_path")
        return columns, rows
