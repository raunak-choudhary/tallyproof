"""Keep breaks append-only and grant the app role read and append access."""

from django.db import migrations

APP = "tallyproof_app"
TABLES = ("recon_break", "break_event")

FORWARD = "".join(
    f"""
CREATE TRIGGER {t}_no_update_delete BEFORE UPDATE OR DELETE ON {t}
  FOR EACH ROW EXECUTE FUNCTION ledger_reject_change();
CREATE TRIGGER {t}_no_truncate BEFORE TRUNCATE ON {t}
  FOR EACH STATEMENT EXECUTE FUNCTION ledger_reject_change();
GRANT SELECT, INSERT ON {t} TO {APP};
"""
    for t in TABLES
)

REVERSE = "".join(
    f"""
DROP TRIGGER IF EXISTS {t}_no_update_delete ON {t};
DROP TRIGGER IF EXISTS {t}_no_truncate ON {t};
REVOKE ALL ON {t} FROM {APP};
"""
    for t in TABLES
)


class Migration(migrations.Migration):
    dependencies = [("reconciliation", "0001_breaks"), ("ledger", "0006_journal_integrity")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
