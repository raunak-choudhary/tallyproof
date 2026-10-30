"""Which records a provable total covers, keyed exactly as the analyst groups them.

The sum tree proves totals by key prefix, so the key decides which totals can be
proven. Keys follow the analyst's views (``apps/analyst/migrations``), so a proven
total and the analyst's SQL total over the same checkpoint are the same number:

``(entity, awarding agency, fiscal year, leaf index)``

- **obligations**: ``obligation.recorded`` and ``obligation.adjusted`` events,
  summed on ``amount``. The fiscal year comes from ``action_date``; federal fiscal
  years start on October 1.
- **outlays**: ``outlay.reported`` events, summed on ``period_outlay``, with the
  fiscal year the record reports.
- The awarding agency is not on adjustments or outlays. It comes from the award's
  first ``obligation.recorded`` event within the same checkpoint, as in the views.
  If that event isn't in the checkpoint yet, the agency is empty.

So these totals can be proven: an entity, an entity for one agency, and an entity
for one agency in one fiscal year. A total filtered any other way (by industry
code, or by year across all agencies) is answered as before, with a labelled
sample of its records.

Everything here is computed from the records' own canonical bytes, so anyone with
the log can rebuild the tree and compare its root with the signed one.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from tallyproof_core.sum_tree import Key, SumLeaf

OBLIGATIONS = "obligations"
OUTLAYS = "outlays"
INDEX_WIDTH = 20
"""Leaf indexes are zero-padded so their text sorts in log order."""


class TotalsError(ValueError):
    """Raised when a record's amount isn't a whole number of cents."""


@dataclass(frozen=True)
class Record:
    """One log entry, as the totals need it."""

    leaf_index: int
    event_type: str
    payload: dict[str, Any]
    record_hash: bytes
    """The entry's leaf hash in the Merkle log."""


def cents(value: object) -> int:
    """A decimal amount in minor units. Refuses fractions of a cent rather than rounding."""
    try:
        amount = Decimal(str(value)) * 100
    except InvalidOperation as error:
        raise TotalsError(f"not an amount: {value!r}") from error
    if amount != amount.to_integral_value():
        raise TotalsError(f"{value!r} is not a whole number of cents")
    return int(amount)


def fiscal_year(action_date: object) -> str:
    """The federal fiscal year of an ISO date: 2024-10-01 is in fiscal 2025."""
    if not isinstance(action_date, str) or len(action_date) < 7:
        return ""
    year, month = int(action_date[:4]), int(action_date[5:7])
    return str(year + 1 if month >= 10 else year)


def prefix(entity: str, agency: str | None = None, year: int | None = None) -> Key:
    """The key prefix for a total. A year needs an agency, since the agency comes first."""
    if year is not None and agency is None:
        raise ValueError("a fiscal year can only be proven together with an agency")
    parts: list[str] = [entity]
    if agency is not None:
        parts.append(agency)
        if year is not None:
            parts.append(str(year))
    return tuple(parts)


def leaves(records: Sequence[Record]) -> list[SumLeaf]:
    """Sum-tree leaves for every obligation and outlay among ``records``.

    ``records`` must be every entry of one checkpoint: the first ``n`` leaves of the
    log, in any order.
    """
    agency: dict[str, tuple[int, str]] = {}
    for r in records:
        if r.event_type == "obligation.recorded":
            award = r.payload.get("award_key")
            if isinstance(award, str) and (award not in agency or r.leaf_index < agency[award][0]):
                agency[award] = (r.leaf_index, str(r.payload.get("awarding_agency") or ""))
    out: list[SumLeaf] = []
    for r in records:
        award_agency = agency.get(str(r.payload.get("award_key")), (0, ""))[1]
        index = f"{r.leaf_index:0{INDEX_WIDTH}d}"
        if r.event_type in ("obligation.recorded", "obligation.adjusted"):
            key = (OBLIGATIONS, award_agency, fiscal_year(r.payload.get("action_date")), index)
            amount = r.payload.get("amount")
        elif r.event_type == "outlay.reported":
            year = r.payload.get("fiscal_year")
            key = (OUTLAYS, award_agency, "" if year is None else str(year), index)
            amount = r.payload.get("period_outlay")
        else:
            continue
        out.append(SumLeaf(key, 0 if amount is None else cents(amount), r.record_hash))
    return out


def records_from_canonical(
    entries: Iterable[tuple[int, bytes, bytes]],
) -> list[Record]:
    """Records from ``(leaf index, canonical bytes, leaf hash)`` triples."""
    import json

    out = []
    for index, canonical, leaf in entries:
        document = json.loads(canonical)
        out.append(Record(index, str(document["event_type"]), document.get("payload") or {}, leaf))
    return out
