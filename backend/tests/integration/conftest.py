"""Integration tests run against real containers (``tests/containers.py``).

Everything under this folder is marked ``integration``, so it runs in the
integration job and stays out of the fast unit run.
"""

from pathlib import Path

import pytest

from tests.containers import Database

__all__ = ["Database"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    here = Path(__file__).parent
    for item in items:
        if here in Path(item.fspath).parents:
            item.add_marker(pytest.mark.integration)
