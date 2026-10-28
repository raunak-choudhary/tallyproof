"""Make the database itself enforce the ledger's integrity rules.

- Every indexed column of ``ledger_event`` must match the canonical bytes, and
  the stored leaf hash must be SHA-256(0x00 || bytes). A row can't claim one
  thing in its columns while its proof covers another.
- ``ledger_event``, ``ledger_batch``, and ``dedupe_rejection`` refuse UPDATE,
  DELETE, and TRUNCATE through triggers. Grants already deny these to the
  application role; the triggers also stop the owner by accident.
- ``merkle_log_head`` gets its single row.
"""

from django.db import migrations

APPEND_ONLY = ("ledger_event", "ledger_batch", "dedupe_rejection")

DOCUMENT_MATCH = """
ALTER TABLE ledger_event
  ADD CONSTRAINT ledger_event_leaf_hash_matches
    CHECK (leaf_hash = sha256('\\x00'::bytea || canonical_bytes)),
  ADD CONSTRAINT ledger_event_columns_match_document
    CHECK (
      public_id = ledger_document(canonical_bytes) ->> 'event_id'
      AND idempotency_key = ledger_document(canonical_bytes) ->> 'idempotency_key'
      AND event_type = ledger_document(canonical_bytes) ->> 'event_type'
      AND account_id = ledger_document(canonical_bytes) ->> 'account_id'
    );
"""

DOCUMENT_MATCH_REVERSE = """
ALTER TABLE ledger_event
  DROP CONSTRAINT IF EXISTS ledger_event_leaf_hash_matches,
  DROP CONSTRAINT IF EXISTS ledger_event_columns_match_document;
"""

REJECT_FUNCTION = """
CREATE OR REPLACE FUNCTION ledger_reject_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% on % is not allowed: the table is append-only', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'insufficient_privilege';
END $$;
"""


def _triggers(table: str) -> tuple[str, str]:
    forward = f"""
CREATE TRIGGER {table}_no_update_delete BEFORE UPDATE OR DELETE ON {table}
  FOR EACH ROW EXECUTE FUNCTION ledger_reject_change();
CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
  FOR EACH STATEMENT EXECUTE FUNCTION ledger_reject_change();
"""
    reverse = f"""
DROP TRIGGER IF EXISTS {table}_no_update_delete ON {table};
DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};
"""
    return forward, reverse


class Migration(migrations.Migration):
    dependencies = [("ledger", "0002_event_store")]
    operations = [
        migrations.RunSQL(DOCUMENT_MATCH, DOCUMENT_MATCH_REVERSE),
        migrations.RunSQL(REJECT_FUNCTION, "DROP FUNCTION IF EXISTS ledger_reject_change();"),
        *(migrations.RunSQL(*_triggers(table)) for table in APPEND_ONLY),
        migrations.RunSQL(
            "INSERT INTO merkle_log_head (id, next_leaf_index) VALUES (1, 0) ON CONFLICT DO NOTHING;",
            "DELETE FROM merkle_log_head;",
        ),
    ]
