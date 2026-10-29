"""Expose the leaf of each award's first record next to the fields taken from it.

The obligations and outlays views take PIID and agency from the award's first
``obligation.recorded`` event. That event can sit past the checkpoint an answer
is pinned to, which would let a pinned answer read a later leaf. With
``award_leaf_index`` beside them, the compiler pins that leaf too whenever a
question uses an award field.

New columns go at the end, which ``CREATE OR REPLACE VIEW`` allows; grants and
the dependent awards view stay as they are.
"""

from importlib import import_module

from django.db import migrations

_FIRST_RECORD = """
WITH first_record AS (
  SELECT DISTINCT ON (payload->>'award_key')
         payload->>'award_key' AS award_key,
         leaf_index,
         payload->>'piid' AS piid,
         payload->>'awarding_agency' AS awarding_agency,
         payload->>'funding_agency' AS funding_agency
  FROM public.ledger_event
  WHERE event_type = 'obligation.recorded'
  ORDER BY payload->>'award_key', leaf_index
)"""

_ACTION_DATE = "(e.payload->>'action_date')::date"
_FISCAL_YEAR = (
    f"(EXTRACT(YEAR FROM {_ACTION_DATE})::int + "
    f"CASE WHEN EXTRACT(MONTH FROM {_ACTION_DATE}) >= 10 THEN 1 ELSE 0 END)"
)

FORWARD = f"""
CREATE OR REPLACE VIEW analyst.obligations WITH (security_barrier) AS
{_FIRST_RECORD}
SELECT e.public_id AS event_id,
       e.leaf_index,
       e.event_type,
       e.payload->>'award_key' AS award_key,
       f.piid,
       f.awarding_agency,
       f.funding_agency,
       e.payload->>'modification_number' AS modification_number,
       (e.payload->>'amount')::numeric(19, 2) AS amount,
       {_ACTION_DATE} AS action_date,
       {_FISCAL_YEAR} AS fiscal_year,
       e.payload->>'action_type' AS action_type,
       e.payload->>'naics_code' AS naics_code,
       e.payload->>'psc_code' AS psc_code,
       f.leaf_index AS award_leaf_index
FROM public.ledger_event e
LEFT JOIN first_record f ON f.award_key = e.payload->>'award_key'
WHERE e.event_type IN ('obligation.recorded', 'obligation.adjusted');

CREATE OR REPLACE VIEW analyst.outlays WITH (security_barrier) AS
{_FIRST_RECORD}
SELECT e.public_id AS event_id,
       e.leaf_index,
       e.payload->>'award_key' AS award_key,
       e.payload->>'treasury_account' AS treasury_account,
       (e.payload->>'fiscal_year')::int AS fiscal_year,
       (e.payload->>'fiscal_period')::int AS fiscal_period,
       (e.payload->>'period_outlay')::numeric(19, 2) AS period_outlay,
       (e.payload->>'cumulative_outlay')::numeric(19, 2) AS cumulative_outlay,
       f.piid,
       f.awarding_agency,
       f.leaf_index AS award_leaf_index
FROM public.ledger_event e
LEFT JOIN first_record f ON f.award_key = e.payload->>'award_key'
WHERE e.event_type = 'outlay.reported';
"""


def _statement(module: str, prefix: str) -> str:
    sql: str = import_module(f"apps.analyst.migrations.{module}").FORWARD
    return next(s for s in sql.split(";\n") if s.strip().startswith(prefix)) + ";\n"


# A view can't drop a column in place, so going back recreates the two views as
# they were, and the awards view that depends on them.
REVERSE = (
    "DROP VIEW analyst.awards;\nDROP VIEW analyst.obligations;\nDROP VIEW analyst.outlays;\n"
    + _statement("0001_views", "CREATE VIEW analyst.obligations ")
    + _statement("0002_outlay_award_fields", "CREATE OR REPLACE VIEW analyst.outlays ")
    + _statement("0001_views", "CREATE VIEW analyst.awards ")
    + "GRANT SELECT ON analyst.obligations, analyst.outlays, analyst.awards "
    "TO tallyproof_analyst;\n"
)


class Migration(migrations.Migration):
    dependencies = [("analyst", "0004_answer_grants")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
