# ADR-0013: Derive a double-entry journal from events

- Status: Proposed (MC-01)
- Date: 2026-10-26
- Zone: Open (improvement)

## Context

A finance reviewer will ask "where are the debits and credits?" A list of events is not a ledger in the accounting sense.

## Decision

Derive a small, deterministic double-entry journal from accepted events:

| Event | Debit | Credit |
|---|---|---|
| `invoice.issued` | Accounts Receivable | Revenue |
| `payment.received` (matched) | Cash | Accounts Receivable |
| `payment.received` (unapplied) | Cash | Unapplied Cash |
| `refund.issued` | Refunds / Contra Revenue | Cash |
| `adjustment.posted` | per adjustment type | per adjustment type |
| FX difference | FX Loss or Cash | Cash or FX Gain |

Enforced by a deferred constraint trigger: debits equal credits per entry. Journal lines are append-only; corrections are reversing entries.

## Reasons

- Credibility with a finance audience at low cost.
- Gives the analyst meaningful questions (trial balance, AR aging) with exact answers.
- The journal is **derived** data: re-derivable from verified events, so it does not need its own Merkle log. Its correctness is checked by property tests (every entry balances, trial balance sums to zero).

## Non-goals

Chart-of-accounts configuration, multi-entity consolidation, accrual schedules.
