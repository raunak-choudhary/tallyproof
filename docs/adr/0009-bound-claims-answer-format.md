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

## Implementation notes (2026-10-29)

As built in `backend/apps/analyst/answer.py` and `pipeline.py`:

- **One slot syntax.** Every value is `{{s1}}`, `{{s2}}`, and so on, and each slot carries its kind (money, count, date, text), its meaning, and the citation behind it. The typed prefixes above (`v`, `d`, `n`, `id`) were simpler to explain than to keep the model consistent with.
- **No derived expressions yet.** `{{v3 = v1 - v2}}` isn't implemented; a question needing a difference has to be answered as two values today.
- **Citations and quotes.** Records are cited as `[[c1]]`; regulation sources as `[[q1]]`, with exact quotes given separately and checked as substrings of the cited leaf after collapsing whitespace. When a sentence shows a value without its citation, rendering adds the citation right after the value.
- **Numbers from a source.** A number from a regulation, such as a rate or a form number, is allowed only in a sentence that cites that source, and only when the answer also quotes, word for word, the passage that holds the number. A paraphrased rate with no quote is rejected, so every regulatory number a reader sees is one they can check against the leaf.
- **Repair.** One repair attempt carries the verifier's findings as plain instructions, not just codes.
- **Large totals.** A total over more records than one answer cites (`DB_ANALYST_MAX_ROWS`) is computed over all of them; its citation lists the first records in log order with `sample_of` set to the full count, and the page labels it.
- **Refusal codes.** Thirteen typed reasons, not five: `forecast`, `personal_data`, `judgment_beyond_data`, `out_of_scope`, `no_data`, `no_evidence`, `ambiguous`, `too_broad`, `unsafe_query`, `unverifiable_claim`, `budget_exceeded`, `model_unavailable`, and `no_checkpoint`.
- **The interactive value.** The analyst page lists each value with its meaning and opens the records behind it with Verify. Showing the compiled SQL beside a value is planned with the site.
