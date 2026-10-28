"""Check and rebuild state derived from the ledger.

The journal and reconciliation breaks are pure functions of the ordered log, so
they can always be recomputed. ``journal_drift`` recomputes the journal and
compares it with what is stored, which catches a rule change or an edited row.
``rebuild`` clears a derived view and resets its cursor so the projections
recompute it; derived tables are append-only, so only the owner role may do it.
"""

from collections import defaultdict
from decimal import Decimal

from django.db import connection

from apps.ledger.models import JournalLine, LedgerEvent
from apps.ledger.projections import envelope_of
from tallyproof_core.journal import entry_for

VIEWS = {
    "journal": ("journal_line",),
    "reconciliation": ("break_event", "recon_break"),
}


def journal_drift(limit: int = 20) -> list[str]:
    """Events whose stored journal lines differ from a fresh derivation."""
    stored: dict[int, list[tuple[str, Decimal, Decimal]]] = defaultdict(list)
    for line in JournalLine.objects.order_by("leaf_index", "line_number"):
        stored[line.leaf_index].append((line.account, line.debit, line.credit))
    with connection.cursor() as cursor:
        cursor.execute("SELECT next_leaf_index FROM projection_cursor WHERE name = 'journal'")
        row = cursor.fetchone()
    projected = row[0] if row else 0
    problems: list[str] = []
    for event in LedgerEvent.objects.filter(leaf_index__lt=projected).order_by("leaf_index"):
        expected = [(x.account.value, x.debit, x.credit) for x in entry_for(envelope_of(event))]
        if stored.get(event.leaf_index, []) != expected:
            problems.append(
                f"leaf {event.leaf_index} ({event.public_id}) differs from its derivation"
            )
            if len(problems) >= limit:
                break
    return problems


def rebuild(view: str) -> None:
    """Clear a derived view and reset its cursor. Run as the owner role only."""
    tables = VIEWS[view]
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        if cursor.fetchone()[0] != "tallyproof_owner":
            raise PermissionError(
                "rebuilding derived state needs the owner role (make migrate settings)"
            )
        for table in tables:
            cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
        cursor.execute(f"TRUNCATE {', '.join(tables)}")
        for table in tables:
            cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")
        cursor.execute("UPDATE projection_cursor SET next_leaf_index = 0 WHERE name = %s", [view])
