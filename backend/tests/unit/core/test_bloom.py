import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tallyproof_core.bloom import BloomFilter


def test_sizing_matches_the_standard_formula():
    # n = 1,000,000 and p = 0.001 give about 14.38 million bits and 10 hashes.
    bloom = BloomFilter.for_capacity(1_000_000, 0.001)
    assert 14_377_000 < bloom.num_bits < 14_378_000
    assert bloom.num_hashes == 10


@given(st.lists(st.binary(min_size=1, max_size=64), max_size=300))
def test_never_a_false_negative(keys):
    bloom = BloomFilter.for_capacity(max(len(keys), 1), 0.01)
    for key in keys:
        bloom.add(key)
    assert all(key in bloom for key in keys)


@pytest.mark.parametrize("target", [0.01, 0.001])
def test_measured_false_positive_rate_stays_near_target(target):
    rng = random.Random(20261027)
    capacity = 20_000
    bloom = BloomFilter.for_capacity(capacity, target)
    for _ in range(capacity):
        bloom.add(rng.randbytes(16) + b"member")
    trials = 200_000
    false_positives = sum(rng.randbytes(16) + b"stranger" in bloom for _ in range(trials))
    measured = false_positives / trials
    assert measured < target * 1.5
    assert bloom.expected_false_positive_rate == pytest.approx(target, rel=0.2)


def test_empty_filter_contains_nothing():
    bloom = BloomFilter.for_capacity(100, 0.01)
    assert b"anything" not in bloom
    assert bloom.expected_false_positive_rate == 0


def test_serialization_round_trip_preserves_membership():
    bloom = BloomFilter.for_capacity(1000, 0.01)
    for i in range(500):
        bloom.add(f"key-{i}".encode())
    restored = BloomFilter.from_bytes(bloom.to_bytes())
    assert restored.count == 500
    assert (restored.num_bits, restored.num_hashes) == (bloom.num_bits, bloom.num_hashes)
    assert all(f"key-{i}".encode() in restored for i in range(500))


@pytest.mark.parametrize("data", [b"", b"XXXX" + bytes(16), BloomFilter(64, 3).to_bytes()[:-1]])
def test_corrupt_serialized_filters_are_rejected(data):
    with pytest.raises(ValueError, match="Bloom filter"):
        BloomFilter.from_bytes(data)


@pytest.mark.parametrize(
    ("args", "message"),
    [((4, 3), "num_bits"), ((64, 0), "num_hashes"), ((64, 65), "num_hashes")],
)
def test_invalid_shapes_are_rejected(args, message):
    with pytest.raises(ValueError, match=message):
        BloomFilter(*args)


@pytest.mark.parametrize(
    ("items", "rate", "message"),
    [(0, 0.01, "expected_items"), (10, 0, "false_positive_rate"), (10, 1, "false_positive_rate")],
)
def test_invalid_capacity_arguments_are_rejected(items, rate, message):
    with pytest.raises(ValueError, match=message):
        BloomFilter.for_capacity(items, rate)
