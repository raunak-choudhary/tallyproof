"""Totals keys follow the analyst's views: entity, the award's agency, fiscal year, leaf."""

import hashlib

import pytest

from tallyproof_core.sum_tree import SumTree, verify_total
from tallyproof_core.totals import (
    OBLIGATIONS,
    OUTLAYS,
    Record,
    TotalsError,
    cents,
    fiscal_year,
    leaves,
    prefix,
)


def h(n: int) -> bytes:
    return hashlib.sha256(str(n).encode()).digest()


def recorded(i: int, award: str, agency: str, amount: str, date: str) -> Record:
    payload = {"award_key": award, "awarding_agency": agency, "amount": amount, "action_date": date}
    return Record(i, "obligation.recorded", payload, h(i))


def adjusted(i: int, award: str, amount: str, date: str) -> Record:
    payload = {"award_key": award, "amount": amount, "action_date": date}
    return Record(i, "obligation.adjusted", payload, h(i))


def outlay(i: int, award: str, amount: str, year: int) -> Record:
    payload = {"award_key": award, "period_outlay": amount, "fiscal_year": year}
    return Record(i, "outlay.reported", payload, h(i))


def test_fiscal_years_start_in_october() -> None:
    assert fiscal_year("2024-09-30") == "2024"
    assert fiscal_year("2024-10-01") == "2025"
    assert fiscal_year(None) == ""


def test_cents_are_exact_and_refuse_fractions() -> None:
    assert cents("1250.50") == 125050
    assert cents("-7960.00") == -796000
    with pytest.raises(TotalsError):
        cents("0.001")
    with pytest.raises(TotalsError):
        cents("lots")


def test_adjustments_and_outlays_take_the_agency_of_the_awards_first_record() -> None:
    records = [
        adjusted(0, "A1", "-5.00", "2024-03-01"),  # arrives before its award's record
        recorded(1, "A1", "Energy", "100.00", "2024-02-01"),
        recorded(2, "A1", "Not used", "1.00", "2024-02-02"),  # a later record of the same award
        outlay(3, "A1", "40.00", 2024),
        outlay(4, "A2", "9.00", 2024),  # no recorded obligation in this checkpoint
    ]
    keys = {leaf.key[3]: leaf.key[:3] for leaf in leaves(records)}
    assert keys["00000000000000000000"] == (OBLIGATIONS, "Energy", "2024")
    assert keys["00000000000000000002"] == (OBLIGATIONS, "Energy", "2024")
    assert keys["00000000000000000003"] == (OUTLAYS, "Energy", "2024")
    assert keys["00000000000000000004"] == (OUTLAYS, "", "2024")


def test_other_events_are_left_out() -> None:
    cash = Record(0, "cash.moved", {"amount": "5.00"}, h(0))
    assert leaves([cash]) == []


def test_a_proven_total_matches_a_plain_sum() -> None:
    records = [
        recorded(0, "A1", "Energy", "100.00", "2024-02-01"),
        adjusted(1, "A1", "-5.25", "2024-11-01"),
        recorded(2, "B1", "Labor", "7.10", "2024-02-01"),
        outlay(3, "A1", "40.00", 2024),
    ]
    tree = SumTree(leaves(records))
    root = tree.root()
    energy = verify_total(tree.prove(prefix(OBLIGATIONS, "Energy")), root)
    assert energy is not None
    assert (energy.total, energy.count) == (9475, 2)
    fy25 = verify_total(tree.prove(prefix(OBLIGATIONS, "Energy", 2025)), root)
    assert fy25 is not None
    assert fy25.total == -525
    everything = verify_total(tree.prove(prefix(OBLIGATIONS)), root)
    assert everything is not None
    assert everything.total == 10185


def test_a_year_needs_an_agency() -> None:
    with pytest.raises(ValueError, match="agency"):
        prefix(OBLIGATIONS, year=2024)
