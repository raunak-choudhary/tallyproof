"""Reconciliation rules: find places where related ledger events don't agree.

The engine reads events in log order and keeps per-award running totals. Every
break it reports names the events involved, so an answer about a break can cite
and prove them. It is deterministic: the same log always gives the same breaks,
so reconciliation can be rebuilt from the ledger after a rule changes.

Break types (docs/backend-design.md, anomaly catalog):

- ``possible_duplicate_award``: a new award with the same recipient, amount, and
  action date as an earlier, different award.
- ``deobligation_exceeds_award``: an adjustment takes an award's obligations
  below zero.
- ``orphan_outlay``: an outlay against an award never obligated.
- ``outlay_exceeds_obligation``: outlays above the award's obligations, adding up the latest
  cumulative figure for each Treasury account and fiscal year.
- ``late_after_close``: an event reported long after it happened.
- ``recipient_burst``: many new awards to one recipient within an hour, after 30
  days with none (:mod:`tallyproof_core.bursts`).
"""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum

from tallyproof_core.bursts import Award, BurstDetector
from tallyproof_core.events import EventEnvelope, EventType


class BreakType(StrEnum):
    """Every kind of break the rules report."""

    POSSIBLE_DUPLICATE_AWARD = "possible_duplicate_award"
    DEOBLIGATION_EXCEEDS_AWARD = "deobligation_exceeds_award"
    ORPHAN_OUTLAY = "orphan_outlay"
    OUTLAY_EXCEEDS_OBLIGATION = "outlay_exceeds_obligation"
    LATE_AFTER_CLOSE = "late_after_close"
    RECIPIENT_BURST = "recipient_burst"


@dataclass(frozen=True)
class Break:
    """One break and the events behind it, as (event ID, role) pairs."""

    break_type: BreakType
    trigger_event_id: str
    award_key: str
    amount_delta: Decimal | None
    detail: str
    events: tuple[tuple[str, str], ...]

    @property
    def dedupe_key(self) -> str:
        """Identifies the break, so re-running the rules never records it twice."""
        return f"{self.break_type}:{self.trigger_event_id}"


def _involved(*pairs: tuple[str, str]) -> tuple[tuple[str, str], ...]:
    """Each event once, in order: an award's first event can also be the one that breaks it."""
    seen: set[str] = set()
    unique = []
    for event_id, role in pairs:
        if event_id not in seen:
            seen.add(event_id)
            unique.append((event_id, role))
    return tuple(unique)


@dataclass
class _Award:
    obligated: Decimal = Decimal(0)
    first_event_id: str = ""
    # Outlays are cumulative within one Treasury account and fiscal year, so the
    # award's total is the latest figure for each account and year, added up.
    latest_outlays: dict[tuple[str, int], Decimal] = field(default_factory=dict)

    @property
    def outlaid(self) -> Decimal:
        return sum(self.latest_outlays.values(), Decimal(0))


@dataclass
class Reconciler:
    """Running state for the rules, fed one event at a time in log order."""

    late_after: timedelta = timedelta(hours=72)
    tolerance: Decimal = Decimal(0)
    _awards: dict[str, _Award] = field(default_factory=dict)
    _signatures: dict[tuple[str, str, str], tuple[str, str]] = field(default_factory=dict)
    _bursts: BurstDetector = field(default_factory=BurstDetector)

    def apply(self, event: EventEnvelope) -> list[Break]:
        """Update the totals with one event and return the breaks it causes."""
        breaks: list[Break] = []
        payload = event.payload.model_dump(mode="json")
        award_key = str(payload.get("award_key", ""))
        match event.event_type:
            case EventType.OBLIGATION_RECORDED:
                breaks += self._recorded(event, award_key, Decimal(payload["amount"]), payload)
                breaks += self._burst(event, award_key)
            case EventType.OBLIGATION_ADJUSTED:
                breaks += self._adjusted(event, award_key, Decimal(payload["amount"]))
            case EventType.OUTLAY_REPORTED:
                breaks += self._outlay(
                    event,
                    award_key,
                    (str(payload["treasury_account"]), int(payload["fiscal_year"])),
                    Decimal(payload["cumulative_outlay"]),
                )
        lag = event.emitted_at - event.occurred_at
        if lag > self.late_after:
            breaks.append(
                Break(
                    BreakType.LATE_AFTER_CLOSE,
                    event.event_id,
                    award_key,
                    None,
                    f"reported {lag.days} days after it happened",
                    ((event.event_id, "late"),),
                )
            )
        return breaks

    def _burst(self, event: EventEnvelope, award_key: str) -> list[Break]:
        burst = self._bursts.observe(
            Award(event.emitted_at, event.account_id, event.event_id, award_key)
        )
        if burst is None:
            return []
        return [
            Break(
                BreakType.RECIPIENT_BURST,
                event.event_id,
                award_key,
                None,
                f"{len(burst.awards)} new awards to recipient {burst.recipient} within an hour"
                f" from {burst.start:%Y-%m-%d %H:%M} UTC, after 30 days with none",
                tuple((a.event_id, "burst_award") for a in burst.awards),
            )
        ]

    def _award(self, award_key: str, event_id: str) -> _Award:
        award = self._awards.get(award_key)
        if award is None:
            award = self._awards[award_key] = _Award(first_event_id=event_id)
        return award

    def _recorded(
        self, event: EventEnvelope, award_key: str, amount: Decimal, payload: dict[str, object]
    ) -> list[Break]:
        self._award(award_key, event.event_id).obligated += amount
        if amount == 0:
            return []
        signature = (event.account_id, str(amount), str(payload["action_date"]))
        earlier = self._signatures.get(signature)
        if earlier is None:
            self._signatures[signature] = (award_key, event.event_id)
            return []
        earlier_award, earlier_event = earlier
        if earlier_award == award_key:
            return []
        return [
            Break(
                BreakType.POSSIBLE_DUPLICATE_AWARD,
                event.event_id,
                award_key,
                amount,
                f"same recipient, amount, and date as award {earlier_award}",
                ((earlier_event, "original"), (event.event_id, "possible_duplicate")),
            )
        ]

    def _adjusted(self, event: EventEnvelope, award_key: str, amount: Decimal) -> list[Break]:
        award = self._award(award_key, event.event_id)
        award.obligated += amount
        if amount < 0 and award.obligated < -self.tolerance:
            return [
                Break(
                    BreakType.DEOBLIGATION_EXCEEDS_AWARD,
                    event.event_id,
                    award_key,
                    award.obligated,
                    f"obligations fall to {award.obligated} after this de-obligation",
                    _involved((award.first_event_id, "award"), (event.event_id, "deobligation")),
                )
            ]
        return []

    def _outlay(
        self,
        event: EventEnvelope,
        award_key: str,
        account_year: tuple[str, int],
        cumulative: Decimal,
    ) -> list[Break]:
        award = self._awards.get(award_key)
        if award is None:
            self._award(award_key, event.event_id).latest_outlays[account_year] = cumulative
            return [
                Break(
                    BreakType.ORPHAN_OUTLAY,
                    event.event_id,
                    award_key,
                    cumulative,
                    "outlay against an award with no obligations in the ledger",
                    ((event.event_id, "outlay"),),
                )
            ]
        award.latest_outlays[account_year] = cumulative
        excess = award.outlaid - award.obligated
        if excess > self.tolerance:
            return [
                Break(
                    BreakType.OUTLAY_EXCEEDS_OBLIGATION,
                    event.event_id,
                    award_key,
                    excess,
                    f"cumulative outlays exceed obligations by {excess}",
                    _involved((award.first_event_id, "award"), (event.event_id, "outlay")),
                )
            ]
        return []
