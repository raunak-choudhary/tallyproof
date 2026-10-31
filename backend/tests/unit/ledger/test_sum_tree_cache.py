"""The API's sum-tree cache: bounded, kept by use, and never queues behind a build."""

import threading
from collections.abc import Iterator

import pytest

from apps.ledger.api import proofs


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    built: list[int] = []

    def fake_build(tree_size: int) -> object:
        built.append(tree_size)
        return object()

    monkeypatch.setattr(proofs, "build_tree", fake_build)
    proofs.reset()
    yield built
    proofs.reset()


def test_a_tree_is_built_once_and_then_served_from_the_cache(builds: list[int]) -> None:
    first = proofs.sum_tree(100)
    assert proofs.sum_tree(100) is first
    assert builds == [100]


def test_an_older_checkpoint_in_use_stays_cached(builds: list[int]) -> None:
    # An answer pinned to an older checkpoint keeps asking for it; it must not be
    # rebuilt on every request just because newer checkpoints exist.
    for size in (100, 200, 100, 300, 100):
        proofs.sum_tree(size)
    assert builds == [100, 200, 300]


def test_no_more_than_the_limit_are_kept(builds: list[int]) -> None:
    for size in range(1, proofs.SUM_TREES_KEPT + 3):
        proofs.sum_tree(size)
    assert len(proofs._sums) == proofs.SUM_TREES_KEPT


def test_a_second_build_is_refused_while_one_is_running(monkeypatch: pytest.MonkeyPatch) -> None:
    started, release = threading.Event(), threading.Event()

    def slow_build(tree_size: int) -> object:
        started.set()
        release.wait(5)
        return object()

    monkeypatch.setattr(proofs, "build_tree", slow_build)
    proofs.reset()
    worker = threading.Thread(target=proofs.sum_tree, args=(100,))
    worker.start()
    try:
        assert started.wait(5)
        with pytest.raises(proofs.BuildBusyError):
            proofs.sum_tree(200)
    finally:
        release.set()
        worker.join(5)
        proofs.reset()
