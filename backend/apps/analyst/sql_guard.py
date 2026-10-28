"""Guard for the fallback path: model-written SQL, treated as hostile input.

Most questions never reach this. The model fills in a query spec and the server
compiles it (ADR-0014). Questions the spec can't express may fall back to SQL the
model writes, and this guard decides whether that SQL may run. It parses the SQL
with sqlglot and accepts it only if every part of the tree is on an allowlist:

- exactly one SELECT; no other statement, no data-modifying or recursive CTE;
- relations: the analyst views only, unqualified (the role's search path pins
  the schema), plus the query's own CTE names;
- columns: those the views expose, plus aliases the query defines;
- node types, functions, and cast targets from fixed allowlists, so anything the
  list doesn't name (``pg_sleep``, set-returning functions, ``LATERAL``, locking
  clauses, ``::regclass``) is refused without having to be foreseen;
- joins need an equality between allowlisted keys, so ``ON true`` can't make a
  cartesian product;
- limits on tree depth and size, and a ``LIMIT`` the guard injects or tightens.

The guard returns SQL re-rendered from the parsed tree, without comments, never the original text,
so whatever the parser saw is exactly what runs. Rejections carry a generic code
and never echo the input. The read-only role is the second layer: it can't write
even when this guard is switched off (``tests/integration/analyst``).
"""

from dataclasses import dataclass
from enum import StrEnum

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

DIALECT = "postgres"
MAX_NODES = 400
MAX_DEPTH = 30
MAX_SQL_CHARS = 4000

VIEW_COLUMNS: dict[str, frozenset[str]] = {
    "obligations": frozenset(
        {
            "event_id",
            "leaf_index",
            "event_type",
            "award_key",
            "piid",
            "awarding_agency",
            "funding_agency",
            "modification_number",
            "amount",
            "action_date",
            "fiscal_year",
            "action_type",
            "naics_code",
            "psc_code",
        }
    ),
    "outlays": frozenset(
        {
            "event_id",
            "leaf_index",
            "award_key",
            "treasury_account",
            "fiscal_year",
            "fiscal_period",
            "period_outlay",
            "cumulative_outlay",
            "piid",
            "awarding_agency",
        }
    ),
    "awards": frozenset(
        {
            "event_id",
            "leaf_index",
            "award_key",
            "piid",
            "awarding_agency",
            "funding_agency",
            "first_action_date",
            "last_action_date",
            "total_obligated",
            "obligation_events",
            "total_outlays",
            "outlay_events",
        }
    ),
    "cash_movements": frozenset(
        {
            "event_id",
            "leaf_index",
            "record_date",
            "fiscal_year",
            "account",
            "direction",
            "category",
            "amount_millions",
        }
    ),
    "breaks": frozenset(
        {"break_id", "break_type", "award_key", "amount_delta", "found_at_leaf_index"}
    ),
    "break_events": frozenset({"break_id", "event_id", "leaf_index", "role"}),
    "journal": frozenset(
        {"event_id", "leaf_index", "entry_id", "line_number", "account", "debit", "credit"}
    ),
}
"""Views the fallback path may read. ``obligation_descriptions`` is left out on
purpose: its text comes from the source data and may carry planted instructions."""

JOIN_KEYS = frozenset({"award_key", "event_id", "break_id", "entry_id"})

ALLOWED_NODES: tuple[type[exp.Expression], ...] = (
    exp.Select, exp.From, exp.Where, exp.Group, exp.Having, exp.Order, exp.Ordered, exp.Limit,
    exp.Distinct, exp.With, exp.CTE, exp.Subquery, exp.Join, exp.Table, exp.TableAlias,
    exp.Alias, exp.Identifier, exp.Column, exp.Star, exp.Literal, exp.Boolean, exp.Null,
    exp.Paren, exp.Tuple, exp.Var,
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.And, exp.Or, exp.Not,
    exp.Is, exp.In, exp.Between, exp.Like, exp.ILike, exp.Exists,
    exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Neg,
    exp.Case, exp.If, exp.Cast, exp.DataType,
    exp.Sum, exp.Count, exp.Min, exp.Max, exp.Avg, exp.Coalesce, exp.Round, exp.Abs,
    exp.Extract, exp.Lower, exp.Upper, exp.Nullif, exp.Greatest, exp.Least,
)  # fmt: skip
"""Every node in an accepted tree must be one of these exact types."""

CAST_TARGETS = frozenset(
    {
        exp.DataType.Type.DECIMAL,
        exp.DataType.Type.INT,
        exp.DataType.Type.BIGINT,
        exp.DataType.Type.DOUBLE,
        exp.DataType.Type.TEXT,
        exp.DataType.Type.VARCHAR,
        exp.DataType.Type.DATE,
    }
)


class Rejection(StrEnum):
    """Why SQL was refused. These codes are all a client ever sees."""

    UNPARSABLE = "unparsable"
    NOT_ONE_SELECT = "not_one_select"
    RELATION = "relation_not_allowed"
    COLUMN = "column_not_allowed"
    CONSTRUCT = "construct_not_allowed"
    CAST = "cast_not_allowed"
    JOIN = "join_not_allowed"
    TOO_COMPLEX = "too_complex"


class GuardError(Exception):
    """SQL the guard refused. The message is the generic code, never the SQL."""

    def __init__(self, code: Rejection) -> None:
        """Keep the code; the message is the code's value."""
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True)
class GuardedQuery:
    """SQL rebuilt from the accepted tree, safe to hand to the analyst role."""

    sql: str
    relations: frozenset[str]


def _parse(sql: str) -> exp.Select:
    if len(sql) > MAX_SQL_CHARS:
        raise GuardError(Rejection.TOO_COMPLEX)
    try:
        statements = sqlglot.parse(sql, dialect=DIALECT)
    except SqlglotError as error:
        raise GuardError(Rejection.UNPARSABLE) from error
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise GuardError(Rejection.NOT_ONE_SELECT)
    return statements[0]


def _depth(node: exp.Expr) -> int:
    depth = 0
    parent = node.parent
    while parent is not None:
        parent = parent.parent
        depth += 1
    return depth


def _check_nodes(tree: exp.Select) -> None:
    nodes = list(tree.walk())
    if len(nodes) > MAX_NODES or max(_depth(n) for n in nodes) > MAX_DEPTH:
        raise GuardError(Rejection.TOO_COMPLEX)
    for node in nodes:
        if type(node) not in ALLOWED_NODES:
            raise GuardError(Rejection.CONSTRUCT)
        if isinstance(node, exp.With) and node.args.get("recursive"):
            raise GuardError(Rejection.CONSTRUCT)
        if isinstance(node, exp.Select) and node.args.get("locks"):
            raise GuardError(Rejection.CONSTRUCT)
        if isinstance(node, exp.DataType) and node.this not in CAST_TARGETS:
            raise GuardError(Rejection.CAST)


def _check_relations(tree: exp.Select) -> frozenset[str]:
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    used: set[str] = set()
    for table in tree.find_all(exp.Table):
        if table.args.get("db") or table.args.get("catalog"):
            raise GuardError(Rejection.RELATION)
        name = table.name
        if name in ctes:
            continue
        if name not in VIEW_COLUMNS:
            raise GuardError(Rejection.RELATION)
        used.add(name)
    if not used:
        raise GuardError(Rejection.RELATION)
    return frozenset(used)


def _check_columns(tree: exp.Select, relations: frozenset[str]) -> None:
    allowed: set[str] = set().union(*(VIEW_COLUMNS[r] for r in relations))
    allowed |= {alias.alias for alias in tree.find_all(exp.Alias)}
    for column in tree.find_all(exp.Column):
        if column.args.get("db") or column.args.get("catalog"):
            raise GuardError(Rejection.COLUMN)
        if not isinstance(column.this, exp.Star) and column.name not in allowed:
            raise GuardError(Rejection.COLUMN)


def _check_joins(tree: exp.Select) -> None:
    for join in tree.find_all(exp.Join):
        if join.args.get("kind") not in (None, "INNER", "OUTER") or join.args.get("method"):
            raise GuardError(Rejection.JOIN)  # CROSS, NATURAL, and friends
        using = join.args.get("using")
        if using:
            if not all(isinstance(u, exp.Identifier) and u.name in JOIN_KEYS for u in using):
                raise GuardError(Rejection.JOIN)
            continue
        on = join.args.get("on")
        keys = [
            eq
            for eq in (on.find_all(exp.EQ) if on is not None else [])
            if isinstance(eq.left, exp.Column)
            and isinstance(eq.right, exp.Column)
            and eq.left.name == eq.right.name
            and eq.left.name in JOIN_KEYS
        ]
        if not keys:
            raise GuardError(Rejection.JOIN)


def _limit(tree: exp.Select, max_rows: int) -> None:
    current = tree.args.get("limit")
    value = None
    if current is not None:
        literal = current.expression
        if not isinstance(literal, exp.Literal) or literal.is_string:
            raise GuardError(Rejection.CONSTRUCT)
        value = int(literal.this)
    if tree.args.get("offset") is not None:
        raise GuardError(Rejection.CONSTRUCT)
    tree.limit(min(value, max_rows) if value is not None else max_rows, copy=False)


def guard(sql: str, *, max_rows: int) -> GuardedQuery:
    """Accept ``sql`` only if every part is allowlisted, and return it rebuilt.

    Raises:
        GuardError: With a generic code, if anything in the SQL is not allowed.
    """
    tree = _parse(sql)
    _check_nodes(tree)
    relations = _check_relations(tree)
    _check_columns(tree, relations)
    _check_joins(tree)
    _limit(tree, max_rows)
    return GuardedQuery(tree.sql(dialect=DIALECT, comments=False), relations)
