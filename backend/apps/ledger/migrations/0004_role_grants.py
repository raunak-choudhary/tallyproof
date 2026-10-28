"""Grant each database role exactly what it needs.

The roles themselves are created outside Django by
``infra/postgres/create-roles.sql``. Every statement here is safe to run again.

- ``tallyproof_app`` can read and append to the ledger, move the log head and
  consumer offsets forward, and write the outbox. It can never update, delete
  from, or truncate the append-only tables.
- ``tallyproof_analyst`` sees only the ``analyst`` schema, whose views arrive
  with the analyst. Default privileges extend its read access to views created
  there later.
"""

from django.db import migrations

APP = "tallyproof_app"
ANALYST = "tallyproof_analyst"

FORWARD = f"""
GRANT SELECT, INSERT ON ledger_event, ledger_batch, dedupe_rejection TO {APP};
REVOKE UPDATE, DELETE, TRUNCATE ON ledger_event, ledger_batch, dedupe_rejection FROM {APP};
GRANT SELECT, UPDATE (next_leaf_index) ON merkle_log_head TO {APP};
GRANT SELECT, INSERT, UPDATE (next_offset, generation, updated_at) ON consumer_offset TO {APP};
GRANT SELECT, INSERT, UPDATE (published_at) ON outbox TO {APP};
GRANT SELECT ON django_content_type, django_migrations TO {APP};
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO {APP};

CREATE SCHEMA IF NOT EXISTS analyst;
REVOKE ALL ON SCHEMA analyst FROM PUBLIC;
GRANT USAGE ON SCHEMA analyst TO {ANALYST};
GRANT SELECT ON ALL TABLES IN SCHEMA analyst TO {ANALYST};
ALTER DEFAULT PRIVILEGES IN SCHEMA analyst GRANT SELECT ON TABLES TO {ANALYST};
"""

REVERSE = f"""
ALTER DEFAULT PRIVILEGES IN SCHEMA analyst REVOKE SELECT ON TABLES FROM {ANALYST};
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE ON SEQUENCES FROM {APP};
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP};
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP};
DROP SCHEMA IF EXISTS analyst;
"""


class Migration(migrations.Migration):
    dependencies = [("ledger", "0003_integrity"), ("contenttypes", "0002_remove_content_type_name")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
