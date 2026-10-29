"""Compile a validated query spec into SQL over the analyst views (ADR-0014).

The compiler only ever emits SQL it builds itself. Table and column names come
from the catalog, never from the spec's text, and every value is a bound
parameter. Each query is pinned to a checkpoint's tree size, so every row it
reads is covered by that signed checkpoint and can be proven.

Alongside the SQL, the compiler renders the filter in plain words. The answer
shows those words next to each value, so a wrong filter is visible to the reader
even when every cited row verifies.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.analyst.query_spec import CATALOG, MAX_LIST_ROWS, Entity, QuerySpec, parse_value

Param = str | int | Decimal | date | list[str] | list[int] | list[Decimal] | list[date]

_SQL_OP = {"eq": "=", "lt": "<", "lte": "<=", "gt": ">", "gte": ">="}
_WORDS_OP = {
    "eq": "is",
    "ne": "is not",
    "lt": "is below",
    "lte": "is at most",
    "gt": "is above",
    "gte": "is at least",
    "in": "is one of",
}
_METRIC_WORDS = {
    "sum_amount": "total",
    "count": "number",
    "min_amount": "smallest",
    "max_amount": "largest",
}

ABSENCE_RULES = {
    "outlay_without_recorded_award": (
        "NOT EXISTS (SELECT 1 FROM analyst.obligations b WHERE b.award_key = t.award_key "
        "AND b.event_type = 'obligation.recorded' AND b.leaf_index < %s)",
        "with no recorded obligation for their award",
    ),
}


@dataclass(frozen=True)
class CompiledQuery:
    """SQL for the bound value and for the evidence behind it, plus the filter in words.

    ``value_sql`` is ``None`` for shapes whose answer is the evidence rows
    themselves. ``evidence_sql`` returns the citable ID and leaf index first.
    ``evidence_limit`` is one more than the caller may cite, so the caller can
    tell a complete evidence set from a truncated one.
    """

    shape: str
    words: str
    evidence_sql: str
    evidence_params: list[Param]
    evidence_limit: int
    value_sql: str | None = None
    value_params: list[Param] = field(default_factory=list)
    group_column: str | None = None


AWARDS_AS_OF = """(
  SELECT f.event_id, f.leaf_index, f.award_key, f.piid, f.awarding_agency,
         f.funding_agency, o.first_action_date, o.last_action_date, o.total_obligated,
         o.obligation_events,
         coalesce(p.total_outlays, 0)::numeric(19, 2) AS total_outlays,
         coalesce(p.outlay_events, 0) AS outlay_events
  FROM (SELECT DISTINCT ON (award_key) award_key, event_id, leaf_index, piid,
               awarding_agency, funding_agency
        FROM analyst.obligations
        WHERE event_type = 'obligation.recorded' AND leaf_index < %s
        ORDER BY award_key, leaf_index) f
  JOIN (SELECT award_key, sum(amount) AS total_obligated, count(*) AS obligation_events,
               min(action_date) AS first_action_date, max(action_date) AS last_action_date
        FROM analyst.obligations WHERE leaf_index < %s GROUP BY award_key) o USING (award_key)
  LEFT JOIN (SELECT award_key, sum(period_outlay) AS total_outlays, count(*) AS outlay_events
             FROM analyst.outlays WHERE leaf_index < %s GROUP BY award_key) p USING (award_key)
)"""
"""The awards view as of a checkpoint. The ``analyst.awards`` view adds up every
leaf in the log; this derived table adds up only the leaves before the checkpoint,
so its three ``%s`` all take the tree size."""

PINNED_SOURCES = {"awards": (AWARDS_AS_OF, 3)}
"""Entities read from a derived table instead of their view, and its parameter count."""


def _quote(identifier: str) -> str:
    # Catalog names are plain lowercase words; quoting is belt and braces.
    if not identifier.replace("_", "").isalnum() or not identifier.islower():
        raise ValueError(f"unexpected identifier {identifier!r}")
    return f'"{identifier}"'


def _render(value: object) -> str:
    return f"{value:,.2f}" if isinstance(value, Decimal) else str(value)


def _where(spec: QuerySpec, entity: Entity, tree_size: int) -> tuple[str, list[Param], str]:
    clauses = [f"t.{_quote(entity.leaf_column)} < %s"]
    params: list[Param] = [tree_size]
    words: list[str] = []
    used = {f.field for f in spec.filters} | set(spec.fields)
    used |= {name for name in (spec.group_by, spec.order_by) if name is not None}
    if used & entity.award_fields:
        # The award's agency and PIID come from its first record; as of this
        # checkpoint, an award first recorded later has neither.
        clauses.append('t."award_leaf_index" < %s')
        params.append(tree_size)
    for f in spec.filters:
        catalog_field = entity.fields[f.field]
        column = f"t.{_quote(catalog_field.column)}"
        if f.op == "in":
            assert isinstance(f.value, list)  # noqa: S101 - guaranteed by spec validation
            values = [parse_value(catalog_field, v) for v in f.value]
            clauses.append(f"{column} = ANY(%s)")
            params.append(values)  # type: ignore[arg-type]
            shown = ", ".join(_render(v) for v in values)
        else:
            value = parse_value(catalog_field, f.value)
            op = "IS DISTINCT FROM" if f.op == "ne" else _SQL_OP[f.op]
            clauses.append(f"{column} {op} %s")
            params.append(value)
            shown = _render(value)
        words.append(f"{catalog_field.words} {_WORDS_OP[f.op]} {shown}")
    return " AND ".join(clauses), params, " and ".join(words)


def compile_spec(spec: QuerySpec, *, tree_size: int, max_rows: int) -> CompiledQuery:
    """Compile ``spec`` against the log as of ``tree_size``, citing at most ``max_rows`` rows."""
    entity = CATALOG[spec.entity]
    view = f"analyst.{_quote(entity.view)}"
    where, params, conditions = _where(spec, entity, tree_size)
    if spec.entity in PINNED_SOURCES:
        view, count = PINNED_SOURCES[spec.entity]
        params = [*([tree_size] * count), *params]
    citable = f"t.{_quote(entity.id_column)}, t.{_quote(entity.leaf_column)}"
    leaf = f"t.{_quote(entity.leaf_column)}"
    subject = entity.words + (f" where {conditions}" if conditions else "")
    limit = max_rows + 1

    if spec.shape == "aggregate":
        assert spec.metric is not None  # noqa: S101 - guaranteed by spec validation
        amount = f"t.{_quote(entity.amount)}" if entity.amount else None
        expr = {
            "sum_amount": f"coalesce(sum({amount}), 0)",
            "count": "count(*)",
            "min_amount": f"min({amount})",
            "max_amount": f"max({amount})",
        }[spec.metric]
        metric_words = _METRIC_WORDS[spec.metric]
        amount_column = f", {amount}" if amount else ""
        if spec.group_by is not None:
            group = f"t.{_quote(entity.fields[spec.group_by].column)}"
            # Records whose group is unknown (a modification whose award falls before
            # the slice has no agency) aren't a group; leave them out, and say so.
            where = f"{where} AND {group} IS NOT NULL"
            # Unranked, fetch one group past the cap so the pipeline can tell it was hit.
            top = f" LIMIT {int(spec.limit) if spec.limit else MAX_LIST_ROWS + 1}"
            order = "DESC" if spec.descending else "ASC"
            value_sql = (
                f"SELECT {group} AS grp, {expr} AS value, count(*) AS row_count FROM {view} t "
                f"WHERE {where} GROUP BY {group} ORDER BY value {order} NULLS LAST, grp{top}"
            )
            evidence_sql = (
                f"SELECT {citable}, {group} AS grp{amount_column} FROM {view} t "
                f"WHERE {where} ORDER BY {leaf} LIMIT {limit}"
            )
            by = entity.fields[spec.group_by].words
            ranked = f", top {spec.limit} by {metric_words}" if spec.limit else ""
            words = (
                f"{metric_words} of {subject}, by {by}{ranked}, leaving out records with no {by}"
            )
            return CompiledQuery(
                spec.shape, words, evidence_sql, list(params), limit, value_sql, params, "grp"
            )
        value_sql = f"SELECT {expr} AS value, count(*) AS row_count FROM {view} t WHERE {where}"
        if spec.metric in ("min_amount", "max_amount"):
            direction = "DESC" if spec.metric == "max_amount" else "ASC"
            extra = "".join(f", t.{_quote(entity.fields[n].column)}" for n in spec.fields)
            evidence_sql = (
                f"SELECT {citable}{amount_column}{extra} FROM {view} t WHERE {where} "
                f"ORDER BY {amount} {direction}, {leaf} LIMIT 1"
            )
        else:
            evidence_sql = (
                f"SELECT {citable}{amount_column} FROM {view} t "
                f"WHERE {where} ORDER BY {leaf} LIMIT {limit}"
            )
        return CompiledQuery(
            spec.shape,
            f"{metric_words} of {subject}",
            evidence_sql,
            list(params),
            limit,
            value_sql,
            params,
        )

    columns = "".join(f", t.{_quote(entity.fields[name].column)}" for name in spec.fields)
    if spec.shape == "list":
        assert spec.limit is not None  # noqa: S101 - guaranteed by spec validation
        order = f"t.{_quote(spec.order_by)}" if spec.order_by else leaf
        direction = "DESC" if spec.descending else "ASC"
        evidence_sql = (
            f"SELECT {citable}{columns} FROM {view} t WHERE {where} "
            f"ORDER BY {order} {direction} NULLS LAST, {leaf} LIMIT {int(spec.limit)}"
        )
        ordered = (
            f", {spec.limit} largest by {entity.fields[spec.order_by].words}"
            if spec.order_by and spec.descending
            else f", first {spec.limit}"
        )
        return CompiledQuery(spec.shape, subject + ordered, evidence_sql, params, spec.limit)

    if spec.shape == "lookup":
        evidence_sql = (
            f"SELECT {citable}{columns} FROM {view} t WHERE {where} ORDER BY {leaf} LIMIT 2"
        )
        return CompiledQuery(spec.shape, f"the one row of {subject}", evidence_sql, params, 2)

    assert spec.absence_rule is not None  # noqa: S101 - guaranteed by spec validation
    rule, rule_words = ABSENCE_RULES[spec.absence_rule]
    amount = f", t.{_quote(entity.amount)}" if entity.amount else ""
    evidence_sql = (
        f"SELECT {citable}, t.award_key{amount} FROM {view} t "
        f"WHERE {where} AND {rule} ORDER BY {leaf} LIMIT {limit}"
    )
    return CompiledQuery(
        spec.shape, f"{subject} {rule_words}", evidence_sql, [*params, tree_size], limit
    )
