from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from tallyproof_core.events import EventEnvelope
from tallyproof_core.journal import Account, entry_for, trial_balance
from tests.unit.pipeline.test_overlay import cash_event, real_events

amounts = st.decimals(min_value=-(10**9), max_value=10**9, places=2, allow_nan=False)


def with_amount(amount: Decimal, index: int = 0) -> EventEnvelope:
    event = real_events(index + 1)[index]
    payload = {**event.payload.model_dump(mode="json"), "amount": str(amount)}
    return event.model_copy(update={"payload": type(event.payload).model_validate(payload)})


@given(st.lists(amounts, min_size=1, max_size=30))
def test_every_entry_balances_and_the_trial_balance_is_zero(values):
    lines = []
    for amount in values:
        entry = entry_for(with_amount(amount))
        assert sum(line.debit for line in entry) == sum(line.credit for line in entry)
        assert all((line.debit > 0) != (line.credit > 0) for line in entry)
        lines += entry
    assert sum(trial_balance(lines).values(), Decimal(0)) == 0


def test_an_obligation_moves_authority_to_unpaid_and_a_deobligation_reverses_it():
    obligate = entry_for(with_amount(Decimal("500.00")))
    assert [(line.account, line.debit, line.credit) for line in obligate] == [
        (Account.AVAILABLE_AUTHORITY, Decimal("500.00"), 0),
        (Account.OBLIGATIONS_UNPAID, 0, Decimal("500.00")),
    ]
    reverse = entry_for(with_amount(Decimal("-200.00")))
    assert trial_balance(obligate + reverse)[Account.OBLIGATIONS_UNPAID] == Decimal("-300.00")


def test_zero_amounts_post_nothing():
    assert entry_for(with_amount(Decimal(0))) == []


def test_treasury_cash_is_converted_from_millions():
    lines = entry_for(cash_event())  # a 12,345 million deposit
    assert lines[0].account is Account.TREASURY_OPERATING_CASH
    assert lines[0].debit == Decimal(12_345_000_000)
