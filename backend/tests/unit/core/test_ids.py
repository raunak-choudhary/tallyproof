import random
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tallyproof_core.ids import PREFIXES, new_id, parse_id

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def test_id_has_prefix_and_26_character_body():
    value = new_id("evt", now=NOW, rng=random.Random(1))
    prefix, body = value.split("_")
    assert prefix == "evt"
    assert len(body) == 26


def test_same_seed_and_time_give_the_same_id():
    assert new_id("ans", now=NOW, rng=random.Random(42)) == new_id(
        "ans", now=NOW, rng=random.Random(42)
    )


def test_ids_sort_by_creation_time():
    earlier = new_id("evt", now=NOW, rng=random.Random(9))
    later = new_id("evt", now=NOW + timedelta(milliseconds=1), rng=random.Random(1))
    assert earlier < later


def test_parse_returns_prefix_and_millisecond_timestamp():
    prefix, created = parse_id(new_id("bat", now=NOW, rng=random.Random(3)))
    assert prefix == "bat"
    assert created == NOW


def test_default_sources_produce_valid_unique_ids():
    first, second = new_id("qry"), new_id("qry")
    assert first != second
    assert parse_id(first, expected_prefix="qry")[0] == "qry"


@pytest.mark.parametrize(
    "value",
    [
        "evt_01JBXQ4V6Z9GQ1W8R3T5Y7U2P",  # too short
        "evt_01JBXQ4V6Z9GQ1W8R3T5Y7U2PI",  # I is not in Crockford base32
        "xyz_01JBXQ4V6Z9GQ1W8R3T5Y7U2PA",  # unknown prefix
        "EVT_01JBXQ4V6Z9GQ1W8R3T5Y7U2PA",  # prefixes are lowercase
        "8ZZZZZZZZZZZZZZZZZZZZZZZZZ",  # no prefix
        "evt_8ZZZZZZZZZZZZZZZZZZZZZZZZZ",  # overflows 128 bits
    ],
)
def test_malformed_ids_are_rejected(value):
    with pytest.raises(ValueError, match="not a valid ID"):
        parse_id(value)


def test_wrong_prefix_is_rejected():
    with pytest.raises(ValueError, match="expected a ans_ ID"):
        parse_id(new_id("evt", now=NOW, rng=random.Random(1)), expected_prefix="ans")


def test_invalid_arguments_are_rejected():
    with pytest.raises(ValueError, match="unknown ID prefix"):
        new_id("acct", now=NOW)
    with pytest.raises(ValueError, match="timezone aware"):
        new_id("evt", now=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="range"):
        new_id("evt", now=datetime(1969, 1, 1, tzinfo=UTC))


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
LATEST = datetime(9999, 12, 31, 23, 59, 59, 999000, tzinfo=UTC)


def test_millisecond_that_float_conversion_used_to_drop_is_preserved():
    # Found by Hypothesis: int(timestamp() * 1000) turned 514901 ms into 514900.
    created = EPOCH + timedelta(milliseconds=514901)
    assert parse_id(new_id("evt", now=created, rng=random.Random(1)))[1] == created


def test_id_with_timestamp_past_year_9999_is_rejected_not_crashed():
    with pytest.raises(ValueError, match="not a valid ID"):
        parse_id("evt_7ZZZZZZZZZZZZZZZZZZZZZZZZZ")


@given(
    prefix=st.sampled_from(sorted(PREFIXES)),
    created=st.datetimes(
        min_value=EPOCH.replace(tzinfo=None), max_value=LATEST.replace(tzinfo=None)
    ),
    seed=st.integers(0, 2**32),
)
def test_round_trip_preserves_prefix_and_time(prefix, created, seed):
    created = created.replace(microsecond=created.microsecond // 1000 * 1000, tzinfo=UTC)
    parsed_prefix, parsed_time = parse_id(new_id(prefix, now=created, rng=random.Random(seed)))
    assert parsed_prefix == prefix
    assert parsed_time == created
