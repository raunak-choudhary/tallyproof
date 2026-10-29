"""The query spec: what the model may ask for instead of writing SQL (ADR-0014).

A spec names a shape, an entity, a metric, and filters, all drawn from the catalog
below. Anything outside the catalog fails validation before any SQL exists, and
filter values are parsed into their field's type, so they can only ever reach the
database as bound parameters.

Each shape has a defined provenance, which is what makes citations honest:

- ``aggregate``: a metric over the filtered rows; every contributing row is cited.
- ``list``: rows in a stated order; each listed row is cited.
- ``lookup``: the fields of exactly one row; that row is cited.
- ``absence``: rows for which a named rule finds no match, cited as "not found in
  the log at this checkpoint".
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldType(StrEnum):
    """How a filter value is parsed and how it is rendered in words."""

    TEXT = "text"
    INTEGER = "integer"
    MONEY = "money"
    DATE = "date"


@dataclass(frozen=True)
class CatalogField:
    """One column a spec may filter, group, list, or order by."""

    column: str
    type: FieldType
    words: str
    groupable: bool = False


@dataclass(frozen=True)
class Entity:
    """One analyst view, its citable ID, and the fields a spec may use."""

    view: str
    words: str
    id_column: str
    amount: str | None
    fields: dict[str, CatalogField]
    leaf_column: str = "leaf_index"


def _f(column: str, kind: FieldType, words: str, *, group: bool = False) -> CatalogField:
    return CatalogField(column, kind, words, group)


_T, _I, _M, _D = FieldType.TEXT, FieldType.INTEGER, FieldType.MONEY, FieldType.DATE

CATALOG: dict[str, Entity] = {
    "obligations": Entity(
        view="obligations",
        words="obligations and modifications",
        id_column="event_id",
        amount="amount",
        fields={
            "award_key": _f("award_key", _T, "award key"),
            "piid": _f("piid", _T, "contract number (PIID)"),
            "awarding_agency": _f("awarding_agency", _T, "awarding agency", group=True),
            "funding_agency": _f("funding_agency", _T, "funding agency", group=True),
            "event_type": _f("event_type", _T, "event type", group=True),
            "modification_number": _f("modification_number", _T, "modification number"),
            "amount": _f("amount", _M, "amount"),
            "action_date": _f("action_date", _D, "action date"),
            "fiscal_year": _f("fiscal_year", _I, "fiscal year", group=True),
            "action_type": _f("action_type", _T, "action type", group=True),
            "naics_code": _f("naics_code", _T, "NAICS code", group=True),
            "psc_code": _f("psc_code", _T, "product or service code", group=True),
        },
    ),
    "outlays": Entity(
        view="outlays",
        words="outlay reports",
        id_column="event_id",
        amount="period_outlay",
        fields={
            "award_key": _f("award_key", _T, "award key"),
            "piid": _f("piid", _T, "contract number (PIID)"),
            "awarding_agency": _f("awarding_agency", _T, "awarding agency", group=True),
            "treasury_account": _f("treasury_account", _T, "Treasury account", group=True),
            "fiscal_year": _f("fiscal_year", _I, "fiscal year", group=True),
            "fiscal_period": _f("fiscal_period", _I, "fiscal period", group=True),
            "period_outlay": _f("period_outlay", _M, "amount paid in the period"),
            "cumulative_outlay": _f("cumulative_outlay", _M, "cumulative amount paid"),
        },
    ),
    "awards": Entity(
        view="awards",
        words="awards",
        id_column="event_id",
        amount="total_obligated",
        fields={
            "award_key": _f("award_key", _T, "award key"),
            "piid": _f("piid", _T, "contract number (PIID)"),
            "awarding_agency": _f("awarding_agency", _T, "awarding agency", group=True),
            "funding_agency": _f("funding_agency", _T, "funding agency", group=True),
            "first_action_date": _f("first_action_date", _D, "first action date"),
            "last_action_date": _f("last_action_date", _D, "last action date"),
            "total_obligated": _f("total_obligated", _M, "total obligated"),
            "total_outlays": _f("total_outlays", _M, "total paid"),
        },
    ),
    "breaks": Entity(
        view="breaks",
        words="reconciliation breaks",
        id_column="break_id",
        amount="amount_delta",
        leaf_column="found_at_leaf_index",
        fields={
            "break_type": _f("break_type", _T, "break type", group=True),
            "award_key": _f("award_key", _T, "award key"),
            "amount_delta": _f("amount_delta", _M, "amount difference"),
        },
    ),
    "cash_movements": Entity(
        view="cash_movements",
        words="Treasury cash movements (millions of dollars)",
        id_column="event_id",
        amount="amount_millions",
        fields={
            "record_date": _f("record_date", _D, "record date"),
            "fiscal_year": _f("fiscal_year", _I, "fiscal year", group=True),
            "account": _f("account", _T, "account", group=True),
            "direction": _f("direction", _T, "direction", group=True),
            "category": _f("category", _T, "category", group=True),
            "amount_millions": _f("amount_millions", _M, "amount in millions"),
        },
    ),
    "journal": Entity(
        view="journal",
        words="journal lines",
        id_column="event_id",
        amount=None,
        fields={
            "account": _f("account", _T, "ledger account", group=True),
            "entry_id": _f("entry_id", _T, "journal entry"),
            "debit": _f("debit", _M, "debit"),
            "credit": _f("credit", _M, "credit"),
        },
    ),
}

EntityName = Literal["obligations", "outlays", "awards", "breaks", "cash_movements", "journal"]
Metric = Literal["sum_amount", "count", "min_amount", "max_amount"]
Op = Literal["eq", "ne", "lt", "lte", "gt", "gte", "in"]
AbsenceRule = Literal["outlay_without_recorded_award"]

MAX_IN_VALUES = 20
MAX_TEXT = 200
MAX_LIST_ROWS = 100


class SpecError(ValueError):
    """A spec that names something outside the catalog or has a mistyped value."""


def parse_value(field: CatalogField, raw: object) -> str | int | Decimal | date:
    """Parse one filter value into its field's type, or raise :class:`SpecError`."""
    try:
        if field.type is FieldType.TEXT:
            if not isinstance(raw, str) or not 0 < len(raw) <= MAX_TEXT:
                raise SpecError(f"{field.column} needs text of 1 to {MAX_TEXT} characters")
            return raw
        if field.type is FieldType.INTEGER:
            if isinstance(raw, bool) or not isinstance(raw, int | str):
                raise SpecError(f"{field.column} needs a whole number")
            return int(raw)
        if field.type is FieldType.MONEY:
            if not isinstance(raw, str | int):
                raise SpecError(f"{field.column} needs a decimal amount as text")
            value = Decimal(str(raw))
            if not value.is_finite():
                raise SpecError(f"{field.column} needs a finite amount")
            return value
        if not isinstance(raw, str):
            raise SpecError(f"{field.column} needs a date as YYYY-MM-DD")
        return date.fromisoformat(raw)
    except (ValueError, InvalidOperation) as error:
        if isinstance(error, SpecError):
            raise
        raise SpecError(f"{field.column}: {raw!r} is not a valid {field.type.value}") from error


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Filter(_Strict):
    """One condition on one catalog field."""

    field: Annotated[str, Field(max_length=64)]
    op: Op
    value: str | int | list[str | int]


class QuerySpec(_Strict):
    """A typed request for data, compiled to SQL by the server, never by the model."""

    shape: Literal["aggregate", "list", "lookup", "absence"]
    entity: EntityName
    metric: Metric | None = None
    filters: Annotated[list[Filter], Field(max_length=8)] = []
    group_by: str | None = None
    fields: Annotated[list[str], Field(max_length=12)] = []
    order_by: str | None = None
    descending: bool = True
    limit: Annotated[int, Field(ge=1, le=MAX_LIST_ROWS)] | None = None
    absence_rule: AbsenceRule | None = None

    @model_validator(mode="after")
    def _fits_the_catalog(self) -> "QuerySpec":
        entity = CATALOG[self.entity]
        for f in self.filters:
            field = entity.fields.get(f.field)
            if field is None:
                raise SpecError(f"{self.entity} has no field {f.field!r}")
            values = f.value if isinstance(f.value, list) else [f.value]
            if (f.op == "in") != isinstance(f.value, list):
                raise SpecError("'in' takes a list of values, every other operator one value")
            if not 0 < len(values) <= MAX_IN_VALUES:
                raise SpecError(f"'in' takes 1 to {MAX_IN_VALUES} values")
            for value in values:
                parse_value(field, value)
        for name in (*self.fields, *filter(None, [self.order_by])):
            if name not in entity.fields:
                raise SpecError(f"{self.entity} has no field {name!r}")
        if self.group_by is not None:
            group = entity.fields.get(self.group_by)
            if group is None or not group.groupable:
                raise SpecError(f"{self.entity} can't be grouped by {self.group_by!r}")
        self._check_shape(entity)
        return self

    def _check_shape(self, entity: Entity) -> None:
        if self.shape == "aggregate":
            if self.metric is None:
                raise SpecError("an aggregate needs a metric")
            if self.metric != "count" and entity.amount is None:
                raise SpecError(f"{self.entity} has no amount to {self.metric}")
            if self.limit is not None and self.group_by is None:
                raise SpecError("only a grouped aggregate can be limited to its top groups")
            if self.order_by or (self.fields and self.metric not in ("min_amount", "max_amount")):
                raise SpecError("only a min or max aggregate takes fields, and none takes order_by")
        elif self.metric is not None or self.group_by is not None:
            raise SpecError(f"a {self.shape} takes no metric or group_by")
        if self.shape == "list" and self.limit is None:
            raise SpecError("a list needs a limit")
        if self.shape == "lookup" and not self.filters:
            raise SpecError("a lookup needs filters that pick out one row")
        if self.shape == "lookup" and (self.order_by or self.limit):
            raise SpecError(
                "a lookup takes no order_by or limit; for the largest or smallest record use "
                "shape aggregate with metric max_amount or min_amount and the fields to show"
            )
        if self.shape == "absence":
            if self.absence_rule is None:
                raise SpecError("an absence question needs a rule")
            if self.entity != "outlays":
                raise SpecError("the only absence rule today is about outlays")
        elif self.absence_rule is not None:
            raise SpecError("only an absence question takes a rule")
