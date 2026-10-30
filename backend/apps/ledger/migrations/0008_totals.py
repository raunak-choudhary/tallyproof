"""Signed Merkle-sum tree roots (ADR-0024), append-only like the checkpoints."""

import django.db.models.functions.datetime
from django.db import migrations, models

APP = "tallyproof_app"

APPEND_ONLY = """
CREATE TRIGGER ledger_totals_no_update_delete BEFORE UPDATE OR DELETE ON ledger_totals
  FOR EACH ROW EXECUTE FUNCTION ledger_reject_change();
CREATE TRIGGER ledger_totals_no_truncate BEFORE TRUNCATE ON ledger_totals
  FOR EACH STATEMENT EXECUTE FUNCTION ledger_reject_change();
"""

APPEND_ONLY_REVERSE = """
DROP TRIGGER IF EXISTS ledger_totals_no_update_delete ON ledger_totals;
DROP TRIGGER IF EXISTS ledger_totals_no_truncate ON ledger_totals;
"""

GRANTS = f"""
GRANT SELECT, INSERT ON ledger_totals TO {APP};
REVOKE UPDATE, DELETE, TRUNCATE ON ledger_totals FROM {APP};
"""


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0007_policy_event_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="LedgerTotals",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("tree_size", models.BigIntegerField(unique=True)),
                ("root_hash", models.BinaryField()),
                ("totals_note", models.TextField()),
                ("records", models.BigIntegerField()),
                (
                    "signed_at",
                    models.DateTimeField(db_default=django.db.models.functions.datetime.Now()),
                ),
            ],
            options={
                "db_table": "ledger_totals",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("tree_size__gt", 0), ("records__gte", 0)),
                        name="ledger_totals_sizes",
                    )
                ],
            },
        ),
        migrations.RunSQL(APPEND_ONLY, APPEND_ONLY_REVERSE),
        migrations.RunSQL(GRANTS, f"REVOKE ALL ON ledger_totals FROM {APP};"),
    ]
