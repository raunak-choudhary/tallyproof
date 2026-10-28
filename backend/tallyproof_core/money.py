"""Exact money amounts.

Money is never a float anywhere in Tallyproof. Amounts arrive as decimal
strings, are held as :class:`decimal.Decimal`, and are written back out in one
fixed format, so the same amount always produces the same bytes and the same
leaf hash.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

CURRENCY_EXPONENTS = {"USD": 2}
"""Supported currencies and their number of decimal places."""

_AMOUNT = re.compile(r"^-?\d{1,15}(\.\d{1,4})?$")


class MoneyError(ValueError):
    """Raised for malformed amounts or operations that mix currencies."""


@dataclass(frozen=True, slots=True)
class Money:
    """An exact amount in a single currency.

    Attributes:
        amount: The value, quantized to the currency's decimal places.
        currency: ISO 4217 code, for example ``"USD"``.
    """

    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        """Validate the currency and normalize the amount to its decimal places."""
        if self.currency not in CURRENCY_EXPONENTS:
            raise MoneyError(f"unsupported currency {self.currency!r}")
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite():
            raise MoneyError("amount must be a finite Decimal")
        quantum = Decimal(1).scaleb(-CURRENCY_EXPONENTS[self.currency])
        normalized = self.amount.quantize(quantum)
        if normalized != self.amount:
            raise MoneyError(f"{self.amount} has more precision than {self.currency} allows")
        # Frozen dataclass: assign the normalized value through object.__setattr__.
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def parse(cls, text: str, currency: str = "USD") -> "Money":
        """Parse a decimal string such as ``"1250.00"`` or ``"-75.5"``.

        Args:
            text: Plain decimal notation. No exponent, separators, or symbols.
            currency: ISO 4217 code.

        Returns:
            The parsed amount.

        Raises:
            MoneyError: If the text is not a plain decimal amount.
        """
        if not _AMOUNT.match(text):
            raise MoneyError(f"not a plain decimal amount: {text!r}")
        try:
            return cls(Decimal(text), currency)
        except InvalidOperation as error:  # pragma: no cover - the regex rules this out
            raise MoneyError(f"not a plain decimal amount: {text!r}") from error

    def __str__(self) -> str:
        """Return the canonical text form, for example ``"1250.00"``."""
        return f"{self.amount:f}"

    def __add__(self, other: "Money") -> "Money":
        """Add two amounts in the same currency."""
        return Money(self.amount + self._same_currency(other).amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        """Subtract two amounts in the same currency."""
        return Money(self.amount - self._same_currency(other).amount, self.currency)

    def __neg__(self) -> "Money":
        """Return the amount with its sign flipped."""
        return Money(-self.amount, self.currency)

    def _same_currency(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise MoneyError(f"cannot combine {self.currency} with {other.currency}")
        return other
