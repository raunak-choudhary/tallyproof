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
| `payment.received` | Cash | Unapplied Cash |
| `payment.applied` (emitted by reconciliation on match) | Unapplied Cash | Accounts Receivable |
| `refund.issued` | Refunds / Contra Revenue | Cash |
| `adjustment.posted` | per adjustment type | per adjustment type |
| FX difference | FX Loss or Cash | Cash or FX Gain |

Every payment posts to Unapplied Cash first. When reconciliation matches it to an invoice, it emits an application entry. This makes the journal a pure function of the ordered log (events plus reconciliation application records by `leaf_index`), so re-derivation is deterministic regardless of arrival order. An earlier draft posted matched payments directly to AR, which depended on reconciliation timing and broke determinism when a payment arrived before its invoice.

Enforced by a deferred constraint trigger: debits equal credits per entry. Journal lines are append-only; corrections are reversing entries.

## Reasons

- Credibility with a finance audience at low cost.
- Gives the analyst meaningful questions (trial balance, AR aging) with exact answers.
- The journal is **derived** data: re-derivable from verified events, so it does not need its own Merkle log. Its correctness is checked by property tests (every entry balances, trial balance sums to zero).

## Non-goals

Chart-of-accounts configuration, multi-entity consolidation, accrual schedules.
