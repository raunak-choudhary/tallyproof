"""Derive a double-entry journal from ledger events (ADR-0013).

Simplified budgetary accounting, with accounts named after their U.S. Standard
General Ledger counterparts. Each entry depends only on its event, so the
journal is a pure function of the ordered log and can always be rebuilt.

A negative amount reverses its event's usual entry: a negative obligation is a
de-obligation, a negative outlay is a recovery. Zero amounts post nothing.
Treasury cash is reported in millions of dollars and converted, so every
account is in dollars and a trial balance across sources means something.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from tallyproof_core.events import EventEnvelope, EventType


class Account(StrEnum):
    """The journal's accounts."""

    AVAILABLE_AUTHORITY = "available_authority"
    OBLIGATIONS_UNPAID = "obligations_unpaid"
    OBLIGATIONS_PAID = "obligations_paid"
    TREASURY_OPERATING_CASH = "treasury_operating_cash"
    RECEIPTS = "receipts"
    DISBURSEMENTS = "disbursements"


UNIT_MULTIPLIERS = {"millions": Decimal(1_000_000)}


@dataclass(frozen=True)
class JournalLine:
    """One side of an entry. Exactly one of debit and credit is non-zero."""

    account: Account
    debit: Decimal
    credit: Decimal


def _pair(debit_account: Account, credit_account: Account, amount: Decimal) -> list[JournalLine]:
    if amount == 0:
        return []
    if amount < 0:  # a reversal: swap the sides and post the absolute amount
        debit_account, credit_account, amount = credit_account, debit_account, -amount
    zero = Decimal(0)
    return [
        JournalLine(debit_account, amount, zero),
        JournalLine(credit_account, zero, amount),
    ]


def entry_for(event: EventEnvelope) -> list[JournalLine]:
    """The balanced journal lines one event posts, possibly none."""
    payload = event.payload.model_dump()
    match event.event_type:
        case EventType.OBLIGATION_RECORDED | EventType.OBLIGATION_ADJUSTED:
            return _pair(
                Account.AVAILABLE_AUTHORITY,
                Account.OBLIGATIONS_UNPAID,
                Decimal(payload["amount"]),
            )
        case EventType.OUTLAY_REPORTED:
            return _pair(
                Account.OBLIGATIONS_UNPAID,
                Account.OBLIGATIONS_PAID,
                Decimal(payload["period_outlay"]),
            )
        case EventType.CASH_MOVEMENT:
            amount = Decimal(payload["amount"]) * UNIT_MULTIPLIERS[payload["unit"]]
            if payload["direction"] == "deposit":
                return _pair(Account.TREASURY_OPERATING_CASH, Account.RECEIPTS, amount)
            return _pair(Account.DISBURSEMENTS, Account.TREASURY_OPERATING_CASH, amount)
        case _:
            return []


def trial_balance(lines: list[JournalLine]) -> dict[Account, Decimal]:
    """Net debit balance per account. The values always sum to zero."""
    balances: dict[Account, Decimal] = {}
    for line in lines:
        balances[line.account] = balances.get(line.account, Decimal(0)) + line.debit - line.credit
    return balances
