# ADR-0014: Constrained query IR compiled to SQL (guarded text-to-SQL, done safely)

- Status: Accepted
- Date: 2026-10-26
- Supersedes: the rule in ADR-0009 that derived provenance from free-form SQL

## Context

Plan review found that deriving "the contributing event IDs" from arbitrary model-written SQL has no defined meaning for anti-joins ("payments with no invoice"), MIN/MAX, top-N, HAVING, window functions, joins, or arithmetic between aggregates. Worse, the most common LLM SQL error (an off-by-one filter like `<` versus `<=`) produces a self-consistent provenance set: the browser re-sums the N rows the query used and gets a match. A wrong total would get a green badge.

## Decision

The model does not write SQL. It writes a **query spec** in a small typed intermediate representation (IR), which the server validates and compiles to SQL:

```text
QuerySpec
  shape:     aggregate | list | lookup | absence      (each has defined provenance semantics)
  metric:    sum_amount | count | min_amount | max_amount   (from a metric catalog)
  entity:    invoices | payments | refunds | open_items | breaks | journal
  filters:   [ {field, op, value} ]   field and op from an allowlist per entity; values typed
  group_by:  [field]                   optional, allowlisted
  as_of:     date                      optional
  order/limit: only for shape=list, with explicit top-N semantics
```

Provenance per shape:

| Shape | Bound value | Cited evidence | What the browser can check |
|---|---|---|---|
| aggregate | metric over filtered rows | every contributing event | recompute metric from cited events; filter shown in words |
| list | rows | each listed event | each row matches its leaf |
| lookup | fields of one row | that event | field values equal verified canonical bytes |
| absence ("no matching invoice") | set of payments | each payment plus the matching rule and checkpoint | each payment verifies; absence is "not found in log at checkpoint N", labeled as such |

Every value chip in the UI shows the compiled filter in plain words ("invoices for acct_X with occurred_at on or before 2026-09-30"). The badge reads **"integrity verified, filter shown"**, never just "verified". A wrong filter is then visible to the reader, and caught by evals.

### Fallback for questions the spec can't express
Questions the IR cannot express may fall back to **guarded free SQL** (sqlglot AST allowlist plus read-only role, threat model 5.3). Those answers are labeled **"lower assurance: integrity of cited rows only, completeness and filter not checked"**. Fallback rate is a reported eval metric. If it is high, the IR grows.

## Reasons

- Provenance has a defined meaning per shape, so citations are honest.
- The attack surface shrinks: the compiler only emits SQL it knows.
- This is how production finance analytics works (semantic layers and metric catalogs), which a data-platform reviewer will recognize.
- Evals can measure "wrong spec" separately from "wrong prose".

## Consequences

- More upfront design (metric catalog, entity fields). Started small: 4 metrics, 6 entities.
- The guarded SQL path still needs the full hardening list, but it is no longer the primary path.

## Implementation notes (2026-10-28)

The catalog follows the federal data rather than the invoice and payment names above: the entities are `obligations`, `outlays`, `awards`, `breaks`, `cash_movements`, and `journal`, one per analyst view (`backend/apps/analyst/query_spec.py`). Two choices were made while building it:

- Every compiled query is pinned to a checkpoint's tree size (`leaf_index < N`), so every row it reads is covered by that signed checkpoint and can be proven against it.
- A grouped aggregate may be limited to its top groups ("which agency obligated the most"), which the original sketch allowed only for lists. Its evidence is every row of the returned groups.

The only absence rule so far is outlays whose award has no recorded obligation.

## Changes after the security review (2026-10-29)

- The guarded SQL path is off unless `ANALYST_SQL_FALLBACK` is set. A question the spec can't express is refused as `not_expressible`. When the fallback is on, its query may select only bare view columns or plain aggregates of them, it is pinned to the checkpoint, and it can't read the awards view.
- Award fields on obligations and outlays (contract number and agencies) come from the award's first record, so a query that uses one also pins that record's leaf (`award_leaf_index`). Award totals are built in the compiled query from leaves before the checkpoint, not read from the `awards` view.
- A grouped aggregate's evidence is fetched per returned group, with the citation cap shared between them, instead of every row of the returned groups. An unranked grouping returns at most 100 groups; more is refused as too broad.
- Filter values must fit their columns: amounts fit `numeric(19, 2)` in whole cents, and integers fit a `bigint`.
