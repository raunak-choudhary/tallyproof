"""Answers are append-only: the app role may insert and read them, nothing else."""

from django.db import migrations

APP = "tallyproof_app"

FORWARD = f"""
CREATE TRIGGER analyst_answer_no_update_delete BEFORE UPDATE OR DELETE ON analyst_answer
  FOR EACH ROW EXECUTE FUNCTION ledger_reject_change();
GRANT SELECT, INSERT ON analyst_answer TO {APP};
"""

REVERSE = f"""
DROP TRIGGER IF EXISTS analyst_answer_no_update_delete ON analyst_answer;
REVOKE ALL ON analyst_answer FROM {APP};
"""


class Migration(migrations.Migration):
    dependencies = [("analyst", "0003_answers")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
