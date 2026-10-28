"""Keep migrations and ORM writes off the analyst's read-only connection."""

from typing import Any


class AnalystDatabaseRouter:
    """Nothing is migrated on, or written through, the ``analyst`` alias."""

    def allow_migrate(self, db: str, app_label: str, **hints: Any) -> bool | None:  # noqa: ANN401
        """Only the default database is ever migrated."""
        return False if db == "analyst" else None
