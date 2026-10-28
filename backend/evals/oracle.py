"""The independent oracle: expected answers computed straight from the dataset files.

This module reads the evaluation dataset's JSON lines, its label manifest, and the
FAR corpus files, and computes each question's expected answer in plain Python.
It imports nothing from the analyst: not its compiler, its views, its routing, or
the reconciliation rules. If the two shared code, a shared bug would let a wrong
answer pass. A test checks the imports.

The ledger's own rules that the oracle must mirror are restated here, not reused:
a redelivered event (same idempotency key) is dropped, an award's agency and PIID
come from its first recording, and a federal fiscal year starts on October 1.
"""

import gzip
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

from evals.dataset import OUT_DIR

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus" / "far"
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Expected:
    """What a correct response contains.

    ``must_cite`` are events a complete answer cites; ``may_cite`` are events it may
    also cite without being wrong (for example the award behind an anomalous
    outlay). Citation precision counts anything outside ``may_cite``.
    """

    refuse: str | None = None
    amount: Decimal | None = None
    count: int | None = None
    group: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    values: frozenset[str] = frozenset()
    section: str | None = None
    must_cite: frozenset[str] = frozenset()
    may_cite: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Record:
    """One event as the oracle sees it: flat fields, after the ledger's dedupe rule."""

    event_id: str
    event_type: str
    award_key: str
    fields: dict[str, Any]


def _fiscal_year(day: date) -> int:
    return day.year + (1 if day.month >= 10 else 0)


class Oracle:
    """Expected answers over one evaluation dataset."""

    def __init__(self, directory: Path = OUT_DIR, corpus: Path = CORPUS_DIR) -> None:
        """Load the dataset, its labels, and the FAR corpus."""
        with gzip.open(directory / "events.jsonl.gz", "rt", encoding="utf-8") as handle:
            raw = [json.loads(line) for line in handle]
        seen: set[str] = set()
        events = []
        for event in raw:
            if event["idempotency_key"] not in seen:
                seen.add(event["idempotency_key"])
                events.append(event)
        first: dict[str, dict[str, Any]] = {}
        for event in events:
            if event["event_type"] == "obligation.recorded":
                first.setdefault(event["payload"]["award_key"], event["payload"])
        self.records = [self._record(e, first) for e in events]
        with (directory / "labels.jsonl").open(encoding="utf-8") as handle:
            self.labels = [json.loads(line) for line in handle]
        self.sections = {
            row["section"]: row
            for path in sorted(corpus.glob("part-*.jsonl"))
            for row in map(json.loads, path.open(encoding="utf-8"))
        }

    @staticmethod
    def _record(event: dict[str, Any], first: dict[str, dict[str, Any]]) -> Record:
        payload = event["payload"]
        award = first.get(payload["award_key"], {})
        flat: dict[str, Any] = {
            "piid": award.get("piid"),
            "awarding_agency": award.get("awarding_agency"),
            "event_type": event["event_type"],
        }
        if event["event_type"].startswith("obligation."):
            day = date.fromisoformat(payload["action_date"])
            flat |= {
                "amount": Decimal(payload["amount"]),
                "action_date": day,
                "fiscal_year": _fiscal_year(day),
                "modification_number": payload.get("modification_number"),
                "naics_code": payload.get("naics_code"),
                "psc_code": payload.get("psc_code"),
            }
        else:
            flat |= {
                "amount": Decimal(payload["period_outlay"]),
                "fiscal_year": payload["fiscal_year"],
                "fiscal_period": payload["fiscal_period"],
                "treasury_account": payload["treasury_account"],
            }
        return Record(event["event_id"], event["event_type"], payload["award_key"], flat)

    def _select(self, expect: dict[str, Any]) -> list[Record]:
        entity = expect.get("entity")
        kinds = {
            "obligations": ("obligation.recorded", "obligation.adjusted"),
            "outlays": ("outlay.reported",),
        }
        wanted = kinds.get(entity or "", ())
        rows = [r for r in self.records if r.event_type in wanted]
        for key in ("awarding_agency", "fiscal_year", "fiscal_period", "piid", "event_type",
                    "modification_number"):  # fmt: skip
            if key in expect:
                rows = [r for r in rows if r.fields.get(key) == expect[key]]
        if "awarding_agency_in" in expect:
            rows = [
                r for r in rows if r.fields.get("awarding_agency") in expect["awarding_agency_in"]
            ]
        if "amount_below" in expect:
            limit = Decimal(expect["amount_below"])
            rows = [r for r in rows if r.fields["amount"] < limit]
        return rows

    def expected(self, expect: dict[str, Any]) -> Expected:
        """The expected answer for one question's ``expect`` block."""
        kind = expect["kind"]
        if kind == "refuse":
            return Expected(refuse=expect["reason"])
        if kind == "policy":
            return Expected(section=expect["section"])
        if kind == "anomalies":
            return self._anomalies(expect)
        rows = self._select(expect)
        ids = frozenset(r.event_id for r in rows)
        if kind == "sum":
            if expect.get("group_by"):
                return Expected(must_cite=ids, may_cite=ids)
            return Expected(
                amount=sum((r.fields["amount"] for r in rows), Decimal(0)),
                count=len(rows),
                must_cite=ids,
                may_cite=ids,
            )
        if kind == "count":
            return Expected(count=len(rows), must_cite=ids, may_cite=ids)
        if kind == "top":
            totals: dict[str, Decimal] = defaultdict(Decimal)
            for r in rows:
                totals[r.fields[expect["group_by"]]] += r.fields["amount"]
            group = min(totals, key=lambda g: (-totals[g], g))
            members = frozenset(r.event_id for r in rows if r.fields[expect["group_by"]] == group)
            return Expected(group=group, amount=totals[group], must_cite=members, may_cite=ids)
        if kind == "average_per_award":
            awards = {r.award_key for r in rows}
            total = sum((r.fields["amount"] for r in rows), Decimal(0))
            mean = (total / len(awards)).quantize(CENT, ROUND_HALF_EVEN) if awards else None
            return Expected(amount=mean, may_cite=ids)
        if kind in ("lookup", "max"):
            if kind == "max":
                rows = sorted(rows, key=lambda r: (-r.fields["amount"], r.event_id))[:1]
            if not rows:
                return Expected(refuse="no_evidence")
            row = rows[0]
            fields = {f: str(row.fields.get(f)) for f in expect.get("fields", [])}
            amount = (
                row.fields["amount"]
                if "amount" in expect.get("fields", []) or kind == "max"
                else None
            )
            only = frozenset({row.event_id})
            return Expected(amount=amount, fields=fields, must_cite=only, may_cite=ids)
        if kind == "distinct":
            values = frozenset(str(r.fields[expect["field"]]) for r in rows)
            return Expected(values=values, must_cite=ids, may_cite=ids)
        if kind == "list":
            return Expected(count=len(rows), must_cite=ids, may_cite=ids)
        raise ValueError(f"unknown expect kind {kind!r}")

    def _anomalies(self, expect: dict[str, Any]) -> Expected:
        labels = [x for x in self.labels if x["anomaly"] == expect["anomaly"] and x["event_id"]]
        by_id = {r.event_id: r for r in self.records}
        if "awarding_agency" in expect:
            wanted = expect["awarding_agency"]
            labels = [
                x for x in labels if by_id[x["event_id"]].fields.get("awarding_agency") == wanted
            ]
        must = frozenset(x["event_id"] for x in labels)
        awards = {by_id[e].award_key for e in must}
        related = {e for x in labels for e in x.get("related_event_ids", [])}
        may = must | related | {r.event_id for r in self.records if r.award_key in awards}
        return Expected(count=len(must), must_cite=must, may_cite=frozenset(may))

    def section_text(self, section: str) -> str:
        """The full text of a FAR section, for checking quotes."""
        return str(self.sections[section]["text"])
