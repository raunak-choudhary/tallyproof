# ADR-0009: Bound-claim answer format (the model never types a number)

- Status: Proposed (MC-01)
- Date: 2026-10-26
- Zone: Open (design of locked AI requirement)

## Context

The brief's differentiator 3 is "every number in an answer is checked against the ledger". Checking numbers after the model writes them is fragile (formatting, rounding, units). Research cited in the README shows numeric accuracy and citation faithfulness are weak even in frontier models.

## Decision

The model writes **templates**, not numbers:

- Values appear only as slots, `{{v1}}`, bound to cells of an executed query result.
- Citations appear only as `[[c1]]`, bound to event IDs or document IDs present in the evidence set for this question.
- Quotes from policy documents are claims of kind `quote` and must be exact substrings of the cited document version.

The **verifier** rejects an answer if:
1. Model-authored text contains numeric tokens outside slots (dates in ISO form that appear verbatim in evidence are allowed by rule).
2. A slot is unbound or a citation references an ID outside the evidence set.
3. A value claim has no provenance. Provenance is defined per query shape by the constrained query IR (ADR-0014), not derived from arbitrary SQL.
4. A quote is not an exact substring.

On rejection, one repair attempt with the verifier's error; then a typed refusal (`unverifiable_claim`, `no_evidence`, `out_of_scope`, `unsafe_query`, `budget_exceeded`).

## Consequences

- Numeric exactness becomes a property of the SQL, not the prose. Errors move to "wrong query", which evals measure.
- Answers can sound slightly templated. Acceptable for finance.
- The UI renders each slot as an interactive value: click to see the SQL, the contributing events, and Verify.
