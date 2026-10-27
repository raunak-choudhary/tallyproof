# ADR-0009: Bound-claim answer format (the model never types a number)

- Status: Accepted
- Date: 2026-10-26

## Context

One of the project's core promises is that every number in an answer is checked against the ledger. Checking numbers after the model writes them is fragile (formatting, rounding, units). Research cited in the README shows numeric accuracy and citation faithfulness are weak even in frontier models.

## Decision

The model writes **templates**, not numbers:

- Values appear only as typed slots bound to the executed query result: `{{v1}}` (money), `{{d1}}` (date), `{{n1}}` (count), `{{id1}}` (identifier). Derived values such as differences are computed server-side as declared expressions (`{{v3 = v1 - v2}}`) and the expression is shown in the UI.
- Citations appear only as `[[c1]]`, bound to event IDs or document IDs present in the evidence set for this question.
- Quotes from policy documents are claims of kind `quote` and must be exact substrings of the cited document version.

The **verifier** rejects an answer if:
1. Model-authored text contains numeric tokens outside slots. Tokens are matched against typed entities, so identifiers like `INV-1042` or `acct_...` that appear in the evidence or the question are allowed, and so are period names ("Q3", "September") that appear in the question.
2. A slot is unbound or a citation references an ID outside the evidence set.
3. A value claim has no provenance. Provenance is defined per query shape by the constrained query IR (ADR-0014), not derived from arbitrary SQL.
4. A quote is not an exact substring.

On rejection, one repair attempt with the verifier's error; then a typed refusal (`unverifiable_claim`, `no_evidence`, `out_of_scope`, `unsafe_query`, `budget_exceeded`).

## Measurement

First-pass and post-repair rejection rates are reported per question category, so an over-strict verifier shows up as a high refusal rate rather than hiding as "safe".

## Consequences

- Numeric exactness becomes a property of the SQL, not the prose. Errors move to "wrong query", which evals measure.
- Answers can sound slightly templated. Acceptable for finance.
- The UI renders each slot as an interactive value: click to see the SQL, the contributing events, and Verify.
