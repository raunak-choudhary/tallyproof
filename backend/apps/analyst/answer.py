"""Bound-claim answers: evidence, the template the model writes, and the verifier (ADR-0009).

The model never types a number. Every value it may mention is a typed slot such
as ``{{s1}}``, bound to a query result; every record it may cite is a label such
as ``[[c1]]``, bound to events in the evidence set; every regulation it may quote
is a source such as ``[[q1]]``, and the quote must be an exact substring of that
source's leaf. The verifier enforces all of it, and a sentence that carries no
slot and no citation is dropped rather than shown.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from apps.analyst.compiler import CompiledQuery
from apps.analyst.query_spec import CATALOG, FieldType, QuerySpec
from apps.analyst.retrieval import Hit

SlotKind = Literal["money", "count", "date", "text"]
Assurance = Literal["filter_shown", "lower_assurance", "policy"]

SLOT = re.compile(r"\{\{\s*(s\d+)\s*\}\}")
CITE = re.compile(r"\[\[\s*([cq]\d+)\s*\]\]")
DIGITS = re.compile(r"\d+")
TOKEN_WITH_DIGIT = re.compile(r"[$A-Za-z0-9][A-Za-z0-9.,$%/_-]*\d[A-Za-z0-9.,%/_-]*|\d")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[{\"(])")


@dataclass(frozen=True)
class Slot:
    """A value the answer may show, and what it means."""

    label: str
    kind: SlotKind
    value: Decimal | int | date | str
    words: str
    citation: str | None = None

    def rendered(self) -> str:
        """The value as a reader sees it."""
        if self.kind == "money" and isinstance(self.value, Decimal):
            sign = "-" if self.value < 0 else ""
            return f"{sign}${abs(self.value):,.2f}"
        if self.kind == "count" and isinstance(self.value, int):
            return f"{self.value:,}"
        return str(self.value)


@dataclass(frozen=True)
class Citation:
    """Events an answer may cite under one label."""

    label: str
    event_ids: tuple[str, ...]
    leaf_indexes: tuple[int, ...]
    words: str


@dataclass(frozen=True)
class QuoteSource:
    """A retrieved policy chunk the answer may quote from."""

    label: str
    event_id: str
    leaf_index: int
    section: str
    title: str
    excerpt: str
    leaf_text: str


@dataclass
class Evidence:
    """Everything an answer may say, and the filter that produced it."""

    slots: dict[str, Slot] = field(default_factory=dict)
    citations: dict[str, Citation] = field(default_factory=dict)
    sources: dict[str, QuoteSource] = field(default_factory=dict)
    filter_words: str = ""
    assurance: Assurance = "filter_shown"
    tree_size: int = 0

    def add_slot(
        self, kind: SlotKind, value: Decimal | int | date | str, words: str, citation: str | None
    ) -> str:
        """Add a slot and return its label."""
        label = f"s{len(self.slots) + 1}"
        self.slots[label] = Slot(label, kind, value, words, citation)
        return label

    def add_citation(self, rows: Sequence[tuple[Any, ...]], words: str) -> str:
        """Add a citation for rows whose first two columns are event ID and leaf index."""
        label = f"c{len(self.citations) + 1}"
        self.citations[label] = Citation(
            label, tuple(r[0] for r in rows), tuple(int(r[1]) for r in rows), words
        )
        return label

    @property
    def empty(self) -> bool:
        """Whether there is nothing at all to say."""
        return not (self.slots or self.citations or self.sources)


_KIND: dict[FieldType, SlotKind] = {
    FieldType.MONEY: "money",
    FieldType.INTEGER: "count",
    FieldType.DATE: "date",
    FieldType.TEXT: "text",
}


def _field_slots(
    evidence: Evidence, spec: QuerySpec, names: Sequence[str], row: tuple[Any, ...], cite: str
) -> None:
    entity = CATALOG[spec.entity]
    for name, value in zip(names, row, strict=True):
        if value is None:
            continue
        catalog_field = entity.fields[name]
        evidence.add_slot(_KIND[catalog_field.type], value, catalog_field.words, cite)


def from_query(
    spec: QuerySpec,
    compiled: CompiledQuery,
    value_rows: Sequence[tuple[Any, ...]],
    evidence_rows: Sequence[tuple[Any, ...]],
    *,
    tree_size: int,
) -> Evidence:
    """Turn a compiled spec's results into slots and citations, per its shape's provenance."""
    evidence = Evidence(filter_words=compiled.words, tree_size=tree_size)
    entity = CATALOG[spec.entity]
    if spec.shape == "aggregate":
        money: SlotKind = "count" if spec.metric == "count" else "money"
        if spec.group_by is None:
            value, row_count = value_rows[0]
            cite = evidence.add_citation(evidence_rows, f"the {row_count:,} records counted")
            if value is not None:
                evidence.add_slot(
                    money, value if money == "money" else int(value), compiled.words, cite
                )
            evidence.add_slot("count", int(row_count), "number of records", cite)
            if spec.fields and evidence_rows:
                _field_slots(evidence, spec, spec.fields, evidence_rows[0][3:], cite)
            return evidence
        group_words = entity.fields[spec.group_by].words
        for group, value, row_count in value_rows:
            rows = [r for r in evidence_rows if r[2] == group]
            cite = evidence.add_citation(rows, f"records where {group_words} is {group}")
            evidence.add_slot("text", str(group), group_words, cite)
            evidence.add_slot(
                money, value if money == "money" else int(value), compiled.words, cite
            )
            evidence.add_slot("count", int(row_count), "number of records", cite)
        return evidence
    if spec.shape in ("list", "lookup"):
        for row in evidence_rows:
            cite = evidence.add_citation([row], f"{entity.words} record {row[0]}")
            _field_slots(evidence, spec, spec.fields, row[2:], cite)
        return evidence
    for row in evidence_rows:  # absence
        cite = evidence.add_citation([row], f"outlay {row[0]} with no recorded award")
        evidence.add_slot("text", row[2], "award key", cite)
        if len(row) > 3 and row[3] is not None:
            evidence.add_slot("money", row[3], "amount paid in the period", cite)
    return evidence


def from_policy(hits: Sequence[Hit], *, tree_size: int) -> Evidence:
    """Policy chunks become quote sources."""
    evidence = Evidence(assurance="policy", tree_size=tree_size)
    for i, hit in enumerate(hits, start=1):
        leaf = hit.chunk.leaf
        evidence.sources[f"q{i}"] = QuoteSource(
            f"q{i}", leaf.event_id, leaf.leaf_index, leaf.section, leaf.title, hit.chunk.text,
            leaf.text,
        )  # fmt: skip
    return evidence


def from_rows(
    columns: Sequence[str], rows: Sequence[tuple[Any, ...]], *, tree_size: int
) -> Evidence:
    """Fallback SQL results: cite rows that carry an event ID, bind every value.

    This path checks only that cited rows are genuine. Completeness and the filter
    aren't checked, and the answer says so.
    """
    evidence = Evidence(
        assurance="lower_assurance",
        filter_words="a query written by the model",
        tree_size=tree_size,
    )
    has_ids = len(columns) > 1 and columns[0] == "event_id" and columns[1] == "leaf_index"
    for row in rows:
        cite = evidence.add_citation([row], f"record {row[0]}") if has_ids else None
        start = 2 if has_ids else 0
        for name, value in zip(columns[start:], row[start:], strict=True):
            if value is None:
                continue
            kind: SlotKind = (
                "money" if isinstance(value, Decimal)
                else "count" if isinstance(value, int)
                else "date" if isinstance(value, date)
                else "text"
            )  # fmt: skip
            evidence.add_slot(kind, value, name.replace("_", " "), cite)
    return evidence


@dataclass(frozen=True)
class Quote:
    """A verbatim quote from one source."""

    source: str
    text: str


@dataclass(frozen=True)
class Draft:
    """What the model wrote: a template and its quotes."""

    template: str
    quotes: tuple[Quote, ...] = ()


@dataclass(frozen=True)
class Verdict:
    """The verifier's decision on a draft."""

    problems: tuple[str, ...]
    sentences: tuple[str, ...]
    """Sentences kept: each carries at least one slot or citation."""
    free_numbers: int = 0

    @property
    def ok(self) -> bool:
        """Whether the draft can be shown."""
        return not self.problems


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _allowed_digits(question: str, evidence: Evidence) -> set[str]:
    allowed = set(DIGITS.findall(question))
    for source in evidence.sources.values():
        allowed.update(DIGITS.findall(source.section))
    return allowed


def verify(draft: Draft, evidence: Evidence, question: str) -> Verdict:
    """Check a draft against the evidence. Problems are short codes the model can fix."""
    problems: list[str] = []
    allowed = _allowed_digits(question, evidence)
    free = 0
    kept: list[str] = []
    for sentence in SENTENCE_END.split(draft.template.strip()):
        slots = SLOT.findall(sentence)
        cites = CITE.findall(sentence)
        for label in slots:
            if label not in evidence.slots:
                problems.append(f"unbound_slot:{label}")
        for label in cites:
            known = evidence.citations if label.startswith("c") else evidence.sources
            if label not in known:
                problems.append(f"unknown_citation:{label}")
        prose = CITE.sub(" ", SLOT.sub(" ", sentence))
        for token in TOKEN_WITH_DIGIT.findall(prose):
            if not set(DIGITS.findall(token)) <= allowed:
                free += 1
                problems.append(f"free_number:{token}")
        if slots or cites:
            kept.append(sentence.strip())
    for quote in draft.quotes:
        source = evidence.sources.get(quote.source)
        if source is None:
            problems.append(f"unknown_citation:{quote.source}")
        elif not quote.text.strip() or _normalize(quote.text) not in _normalize(source.leaf_text):
            problems.append(f"quote_mismatch:{quote.source}")
    if not kept and not draft.quotes:
        problems.append("no_claims")
    return Verdict(tuple(dict.fromkeys(problems)), tuple(kept), free)


def render(sentences: Sequence[str], evidence: Evidence) -> str:
    """Fill slots with their values. Citation markers stay for the reader to open."""
    text = " ".join(sentences)
    return SLOT.sub(lambda m: evidence.slots[m.group(1)].rendered(), text)
