"""Curated views, the only relations the analyst role can read.

Every view exposes ``event_id`` (the event's public ID) and ``leaf_index``, so
any row an answer uses can be cited and proven. Raw bytes, Kafka coordinates,
correlation IDs, and internal keys stay hidden. Free-text descriptions come from
the source data and may contain planted instructions, so they live in their own
view that the query compiler must ask for by name.

Views read ``payload``, which Postgres generates from the canonical bytes, so
what the analyst sees is exactly what the proof covers. They are marked
``security_barrier`` so a predicate the analyst supplies can't run before the
view's own filters and leak rows from other event types.

Federal fiscal years start on October 1: an action dated 2024-10-01 is FY2025.
"""

from django.db import migrations

ANALYST = "tallyproof_analyst"


def _fiscal_year(column: str) -> str:
    return f"(EXTRACT(YEAR FROM {column})::int + CASE WHEN EXTRACT(MONTH FROM {column}) >= 10 THEN 1 ELSE 0 END)"


_ACTION_DATE = "(e.payload->>'action_date')::date"

FORWARD = f"""
CREATE VIEW analyst.obligations WITH (security_barrier) AS
WITH first_record AS (
  SELECT DISTINCT ON (payload->>'award_key')
         payload->>'award_key' AS award_key,
         payload->>'piid' AS piid,
         payload->>'awarding_agency' AS awarding_agency,
         payload->>'funding_agency' AS funding_agency
  FROM public.ledger_event
  WHERE event_type = 'obligation.recorded'
  ORDER BY payload->>'award_key', leaf_index
)
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
       {_fiscal_year(_ACTION_DATE)} AS fiscal_year,
       e.payload->>'action_type' AS action_type,
       e.payload->>'naics_code' AS naics_code,
       e.payload->>'psc_code' AS psc_code
FROM public.ledger_event e
LEFT JOIN first_record f ON f.award_key = e.payload->>'award_key'
WHERE e.event_type IN ('obligation.recorded', 'obligation.adjusted');

CREATE VIEW analyst.obligation_descriptions WITH (security_barrier) AS
SELECT public_id AS event_id, leaf_index, payload->>'description' AS description
FROM public.ledger_event
WHERE event_type IN ('obligation.recorded', 'obligation.adjusted')
  AND payload->>'description' IS NOT NULL;

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

CREATE VIEW analyst.cash_movements WITH (security_barrier) AS
SELECT public_id AS event_id,
       leaf_index,
       (payload->>'record_date')::date AS record_date,
       {_fiscal_year("(payload->>'record_date')::date")} AS fiscal_year,
       payload->>'account' AS account,
       payload->>'direction' AS direction,
       payload->>'category' AS category,
       (payload->>'amount')::numeric(19, 2) AS amount_millions
FROM public.ledger_event
WHERE event_type = 'cash.movement';

CREATE VIEW analyst.breaks WITH (security_barrier) AS
SELECT public_id AS break_id,
       break_type,
       nullif(award_key, '') AS award_key,
       amount_delta::numeric(19, 2) AS amount_delta,
       leaf_index AS found_at_leaf_index
FROM public.recon_break;

CREATE VIEW analyst.break_events WITH (security_barrier) AS
SELECT b.public_id AS break_id, e.public_id AS event_id, e.leaf_index, be.role
FROM public.break_event be
JOIN public.recon_break b ON b.id = be.recon_break_id
JOIN public.ledger_event e ON e.id = be.event_id;

CREATE VIEW analyst.journal WITH (security_barrier) AS
SELECT e.public_id AS event_id,
       j.leaf_index,
       j.entry_id,
       j.line_number,
       j.account,
       j.debit::numeric(19, 2) AS debit,
       j.credit::numeric(19, 2) AS credit
FROM public.journal_line j
JOIN public.ledger_event e ON e.id = j.event_id;

CREATE VIEW analyst.policy_sections WITH (security_barrier) AS
SELECT public_id AS event_id,
       leaf_index,
       payload->>'source' AS source,
       payload->>'citation' AS citation,
       payload->>'section' AS section,
       payload->>'title' AS title,
       (payload->>'edition')::date AS edition
FROM public.ledger_event
WHERE event_type = 'policy.published';

GRANT SELECT ON ALL TABLES IN SCHEMA analyst TO {ANALYST};
"""

VIEWS = (
    "awards",
    "policy_sections",
    "journal",
    "break_events",
    "breaks",
    "cash_movements",
    "outlays",
    "obligation_descriptions",
    "obligations",
)

REVERSE = "".join(f"DROP VIEW IF EXISTS analyst.{v};\n" for v in VIEWS)


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0007_policy_event_type"),
        ("reconciliation", "0002_integrity"),
    ]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
