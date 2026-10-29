"""Take the analyst role's access to source text and the policy view away.

``obligation_descriptions`` holds free text from the source data, which may carry
planted instructions, and ``policy_sections`` is read by the retrieval index, not
by questions. Neither is in the query catalog or the fallback's view list, so the
role that runs questions has no reason to read them.

The blanket default grant on the schema goes too: a view added later is readable
only once a migration grants it by name.
"""

from django.db import migrations

ANALYST = "tallyproof_analyst"

FORWARD = f"""
REVOKE SELECT ON analyst.obligation_descriptions, analyst.policy_sections FROM {ANALYST};
ALTER DEFAULT PRIVILEGES IN SCHEMA analyst REVOKE SELECT ON TABLES FROM {ANALYST};
"""

REVERSE = f"""
ALTER DEFAULT PRIVILEGES IN SCHEMA analyst GRANT SELECT ON TABLES TO {ANALYST};
GRANT SELECT ON analyst.obligation_descriptions, analyst.policy_sections TO {ANALYST};
"""


class Migration(migrations.Migration):
    dependencies = [("analyst", "0005_award_leaf_index"), ("ledger", "0004_role_grants")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
