from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tallyproof_core.money import Money, MoneyError


@pytest.mark.parametrize(
    ("text", "canonical"),
    [("1250", "1250.00"), ("1250.5", "1250.50"), ("-75.00", "-75.00"), ("0", "0.00")],
)
def test_parse_normalizes_to_two_decimal_places(text, canonical):
    assert str(Money.parse(text)) == canonical


@pytest.mark.parametrize(
    "text", ["1e3", "1,250.00", "$12", " 12", "12.", ".5", "NaN", "1.23456", "", "--1"]
)
def test_parse_rejects_anything_but_plain_decimals(text):
    with pytest.raises(MoneyError):
        Money.parse(text)


def test_sub_cent_precision_is_rejected_not_rounded():
    with pytest.raises(MoneyError, match="precision"):
        Money.parse("10.005")


def test_arithmetic_is_exact():
    # 0.1 + 0.2 is the classic float failure.
    assert Money.parse("0.10") + Money.parse("0.20") == Money.parse("0.30")
    assert str(Money.parse("100.00") - Money.parse("100.01")) == "-0.01"
    assert -Money.parse("5.00") == Money.parse("-5.00")


def test_unsupported_currency_and_bad_amounts_are_rejected():
    with pytest.raises(MoneyError, match="unsupported currency"):
        Money(Decimal("1.00"), "EUR")
    with pytest.raises(MoneyError, match="finite"):
        Money(Decimal("Infinity"))
    with pytest.raises(MoneyError, match="finite"):
        Money(1.5)  # type: ignore[arg-type]


def test_mixing_currencies_is_rejected():
    usd = Money.parse("1.00")
    other = object.__new__(Money)
    object.__setattr__(other, "amount", Decimal("1.00"))
    object.__setattr__(other, "currency", "EUR")
    with pytest.raises(MoneyError, match="cannot combine"):
        usd + other


cents = st.integers(-(10**15), 10**15)


@given(cents, cents)
def test_addition_matches_integer_cents(a, b):
    def money(c: int) -> Money:
        return Money(Decimal(c).scaleb(-2))

    assert money(a) + money(b) == money(a + b)


@given(cents)
def test_text_form_round_trips(c):
    value = Money(Decimal(c).scaleb(-2))
    assert Money.parse(str(value)) == value
