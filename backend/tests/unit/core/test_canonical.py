import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tallyproof_core.canonical import MAX_SAFE_INTEGER, CanonicalizationError, canonicalize


def test_keys_are_sorted_by_utf16_code_units_as_in_rfc_8785():
    # Example from RFC 8785 section 3.2.3: an emoji (a surrogate pair in UTF-16)
    # sorts before U+FB33, unlike a plain code point sort.
    value = {
        "€": "Euro Sign",
        "\r": "Carriage Return",
        "דּ": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "\U0001f600": "Emoji: Grinning Face",
        "\u0080": "Control",
        "ö": "Latin Small Letter O With Diaeresis",
    }
    keys = list(json.loads(canonicalize(value)).keys())
    assert keys == ["\r", "1", "\u0080", "ö", "€", "\U0001f600", "דּ"]


def test_output_has_no_insignificant_whitespace():
    assert canonicalize({"b": [1, 2], "a": {"c": None}}) == b'{"a":{"c":null},"b":[1,2]}'


def test_decimal_strings_pass_through_unchanged():
    assert canonicalize({"amount": "1250.00"}) == b'{"amount":"1250.00"}'


@pytest.mark.parametrize("value", [1.5, 0.0, {"amount": 10.25}, [3.0]])
def test_floats_are_rejected(value):
    with pytest.raises(CanonicalizationError, match="floats"):
        canonicalize(value)


@pytest.mark.parametrize("value", [-1, MAX_SAFE_INTEGER + 1, {"n": 2**64}])
def test_integers_outside_the_safe_range_are_rejected(value):
    with pytest.raises(CanonicalizationError, match="outside"):
        canonicalize(value)


def test_largest_safe_integer_is_accepted():
    assert canonicalize(MAX_SAFE_INTEGER) == str(MAX_SAFE_INTEGER).encode()


def test_lone_surrogates_are_rejected():
    with pytest.raises(CanonicalizationError, match="Unicode"):
        canonicalize({"memo": "broken \ud800 text"})


def test_non_string_keys_and_unknown_types_are_rejected():
    with pytest.raises(CanonicalizationError, match="keys"):
        canonicalize({1: "one"})
    with pytest.raises(CanonicalizationError, match="unsupported"):
        canonicalize({"when": object()})


def test_tricky_but_valid_unicode_is_preserved():
    # Zero-width space and a right-to-left override, as planted in injection tests.
    text = "approve​‮invoice"
    assert json.loads(canonicalize({"memo": text}))["memo"] == text


json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(0, MAX_SAFE_INTEGER)
    | st.text(alphabet=st.characters(codec="utf-8")),
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(st.text(alphabet=st.characters(codec="utf-8")), children, max_size=4)
    ),
    max_leaves=20,
)


@given(json_values)
def test_canonicalizing_parsed_output_gives_identical_bytes(value):
    first = canonicalize(value)
    assert canonicalize(json.loads(first)) == first
