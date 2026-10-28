"""Let outlay questions filter by contract number and awarding agency.

Outlay events carry only the award key. Questions are asked by PIID or agency,
so the view joins each outlay to its award's original recording. Orphan outlays,
whose award was never recorded, keep null in both columns.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE VIEW analyst.outlays WITH (security_barrier) AS
WITH first_record AS (
  SELECT DISTINCT ON (payload->>'award_key')
         payload->>'award_key' AS award_key,
         payload->>'piid' AS piid,
         payload->>'awarding_agency' AS awarding_agency
  FROM public.ledger_event
  WHERE event_type = 'obligation.recorded'
  ORDER BY payload->>'award_key', leaf_index
)
SELECT e.public_id AS event_id,
       e.leaf_index,
       e.payload->>'award_key' AS award_key,
       e.payload->>'treasury_account' AS treasury_account,
       (e.payload->>'fiscal_year')::int AS fiscal_year,
       (e.payload->>'fiscal_period')::int AS fiscal_period,
       (e.payload->>'period_outlay')::numeric(19, 2) AS period_outlay,
       (e.payload->>'cumulative_outlay')::numeric(19, 2) AS cumulative_outlay,
       f.piid,
       f.awarding_agency
FROM public.ledger_event e
LEFT JOIN first_record f ON f.award_key = e.payload->>'award_key'
WHERE e.event_type = 'outlay.reported';
"""

# A replaced view can't drop columns, so going back means recreating the view
# and the one that depends on it.
REVERSE = """
DROP VIEW analyst.awards;
DROP VIEW analyst.outlays;
CREATE VIEW analyst.outlays WITH (security_barrier) AS
SELECT public_id AS event_id,
       leaf_index,
       payload->>'award_key' AS award_key,
       payload->>'treasury_account' AS treasury_account,
       (payload->>'fiscal_year')::int AS fiscal_year,
       (payload->>'fiscal_period')::int AS fiscal_period,
       (payload->>'period_outlay')::numeric(19, 2) AS period_outlay,
       (payload->>'cumulative_outlay')::numeric(19, 2) AS cumulative_outlay
FROM public.ledger_event
WHERE event_type = 'outlay.reported';

CREATE VIEW analyst.awards WITH (security_barrier) AS
WITH obligated AS (
  SELECT award_key, sum(amount) AS total_obligated, count(*) AS obligation_events,
         min(action_date) AS first_action_date, max(action_date) AS last_action_date
  FROM analyst.obligations GROUP BY award_key
), paid AS (
  SELECT award_key, sum(period_outlay) AS total_outlays, count(*) AS outlay_events
  FROM analyst.outlays GROUP BY award_key
), first_record AS (
  SELECT DISTINCT ON (award_key) award_key, event_id, leaf_index, piid,
         awarding_agency, funding_agency
  FROM analyst.obligations
  WHERE event_type = 'obligation.recorded'
  ORDER BY award_key, leaf_index
)
SELECT f.event_id,
       f.leaf_index,
       f.award_key,
       f.piid,
       f.awarding_agency,
       f.funding_agency,
       o.first_action_date,
       o.last_action_date,
       o.total_obligated,
       o.obligation_events,
       coalesce(p.total_outlays, 0)::numeric(19, 2) AS total_outlays,
       coalesce(p.outlay_events, 0) AS outlay_events
FROM first_record f
JOIN obligated o USING (award_key)
LEFT JOIN paid p USING (award_key);
GRANT SELECT ON analyst.outlays, analyst.awards TO tallyproof_analyst;
"""


class Migration(migrations.Migration):
    dependencies = [("analyst", "0001_views")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
