"""The Count-Min Sketch never undercounts and stays inside its error bound."""

import collections
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tallyproof_core.sketch import CountMinSketch

keys = st.lists(st.binary(min_size=1, max_size=12), min_size=1, max_size=300)


@settings(max_examples=200)
@given(items=keys, width=st.integers(1, 64), depth=st.integers(1, 6))
def test_an_estimate_is_never_below_the_true_count(
    items: list[bytes], width: int, depth: int
) -> None:
    sketch = CountMinSketch(width, depth)
    for item in items:
        sketch.add(item)
    for key, count in collections.Counter(items).items():
        assert sketch.estimate(key) >= count


def test_add_returns_the_new_estimate() -> None:
    sketch = CountMinSketch(1024, 4)
    assert [sketch.add(b"a") for _ in range(3)] == [1, 2, 3]
    assert sketch.add(b"b", 5) == 5
    assert sketch.total == 8


def test_overcounts_stay_inside_the_bound_almost_always() -> None:
    sketch = CountMinSketch.for_error(epsilon=0.01, delta=0.01)
    stream = [f"recipient-{i % 2000}".encode() for i in range(20_000)]
    for key in stream:
        sketch.add(key)
    bound = sketch.epsilon * sketch.total
    over = sum(sketch.estimate(f"recipient-{i}".encode()) - 10 > bound for i in range(2000))
    assert over / 2000 <= sketch.delta


def test_sizes_follow_the_bounds() -> None:
    sketch = CountMinSketch.for_error(epsilon=0.001, delta=0.001)
    assert sketch.width == math.ceil(math.e / 0.001)
    assert sketch.depth == math.ceil(math.log(1000))
    assert sketch.epsilon <= 0.001
    assert sketch.delta <= 0.001


def test_the_same_keys_land_in_the_same_counters_every_run() -> None:
    a, b = CountMinSketch(97, 3), CountMinSketch(97, 3)
    for key in (b"x", b"y", b"x"):
        a.add(key)
        b.add(key)
    assert [a.estimate(k) for k in (b"x", b"y", b"z")] == [
        b.estimate(k) for k in (b"x", b"y", b"z")
    ]


@pytest.mark.parametrize(("width", "depth"), [(0, 2), (8, 0), (8, 9)])
def test_bad_shapes_are_refused(width: int, depth: int) -> None:
    with pytest.raises(ValueError, match="width must be positive"):
        CountMinSketch(width, depth)


def test_it_only_counts_up() -> None:
    with pytest.raises(ValueError, match="only counts up"):
        CountMinSketch(8, 2).add(b"a", -1)
