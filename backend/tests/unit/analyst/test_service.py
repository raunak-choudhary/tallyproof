from collections.abc import Sequence
from typing import Any

import pytest
from django.core.cache import cache

from apps.analyst import service


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


class Agencies:
    def __init__(self, names: list[str]) -> None:
        self.names = names
        self.calls: list[tuple[str, Sequence[Any]]] = []

    def run(self, sql: str, params: Sequence[Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
        self.calls.append((sql, params))
        return ["awarding_agency"], [(n,) for n in self.names[: int(params[0])]]


def test_the_agency_list_is_read_once_per_checkpoint():
    db = Agencies(["Department of State", "Department of Energy"])
    assert service.agencies(db, tree_size=10) == ["Department of State", "Department of Energy"]
    assert service.agencies(db, tree_size=10) == ["Department of State", "Department of Energy"]
    assert len(db.calls) == 1
    service.agencies(db, tree_size=11)
    assert len(db.calls) == 2


def test_the_agency_list_is_capped():
    db = Agencies([f"Agency {n:04}" for n in range(1000)])
    assert len(service.agencies(db, tree_size=1)) == service.MAX_AGENCIES
    assert db.calls[0][1] == [service.MAX_AGENCIES]
