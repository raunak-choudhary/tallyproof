"""Make every journal entry balance, keep journal lines append-only, and grant access.

The balance check is a deferred constraint trigger, so the lines of one entry
can be inserted one at a time and are checked together when the transaction
commits.
"""

from django.db import migrations

APP = "tallyproof_app"

BALANCE = """
CREATE OR REPLACE FUNCTION journal_entry_balances() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  debits numeric;
  credits numeric;
BEGIN
  SELECT coalesce(sum(debit), 0), coalesce(sum(credit), 0) INTO debits, credits
    FROM journal_line WHERE entry_id = NEW.entry_id;
  IF debits <> credits THEN
    RAISE EXCEPTION 'journal entry % does not balance: debits %, credits %',
      NEW.entry_id, debits, credits USING ERRCODE = 'check_violation';
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER journal_line_balanced AFTER INSERT ON journal_line
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION journal_entry_balances();
CREATE TRIGGER journal_line_no_update_delete BEFORE UPDATE OR DELETE ON journal_line
  FOR EACH ROW EXECUTE FUNCTION ledger_reject_change();
CREATE TRIGGER journal_line_no_truncate BEFORE TRUNCATE ON journal_line
  FOR EACH STATEMENT EXECUTE FUNCTION ledger_reject_change();
"""

BALANCE_REVERSE = """
DROP TRIGGER IF EXISTS journal_line_balanced ON journal_line;
DROP TRIGGER IF EXISTS journal_line_no_update_delete ON journal_line;
DROP TRIGGER IF EXISTS journal_line_no_truncate ON journal_line;
DROP FUNCTION IF EXISTS journal_entry_balances();
"""

GRANTS = f"""
GRANT SELECT, INSERT ON journal_line TO {APP};
REVOKE UPDATE, DELETE, TRUNCATE ON journal_line FROM {APP};
GRANT SELECT, INSERT, UPDATE (next_leaf_index, updated_at) ON projection_cursor TO {APP};
"""


class Migration(migrations.Migration):
    dependencies = [("ledger", "0005_journal_and_cursors")]
    operations = [
        migrations.RunSQL(BALANCE, BALANCE_REVERSE),
        migrations.RunSQL(GRANTS, f"REVOKE ALL ON journal_line, projection_cursor FROM {APP};"),
    ]
