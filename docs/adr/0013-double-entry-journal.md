# ADR-0013: Derive a double-entry journal from events

- Status: Accepted
- Date: 2026-10-26, revised 2026-10-27 for federal budget data

## Context

A finance reader will ask where the debits and credits are. A list of events isn't a ledger in the accounting sense. The first version of this record used company receivables and payables. Once the project moved to real federal spending data ([ADR-0016](0016-real-public-data-sources.md)), the journal needed to follow budgetary accounting instead.

## Decision

Derive a small, deterministic double-entry journal from accepted events, using simplified budgetary accounts named after their U.S. Standard General Ledger counterparts:

| Event | Debit | Credit |
|---|---|---|
| `obligation.recorded` | Available authority | Obligations, unpaid |
| `obligation.adjusted` with a negative amount (de-obligation) | Obligations, unpaid | Available authority |
| `obligation.adjusted` with a positive amount | Available authority | Obligations, unpaid |
| `outlay.reported` (the period's outlay) | Obligations, unpaid | Obligations, paid |
| `cash.movement`, deposit | Treasury operating cash | Receipts |
| `cash.movement`, withdrawal | Disbursements | Treasury operating cash |

Every entry depends only on the event itself, and entries are posted in leaf-index order. An outlay against an award with too little unpaid obligation still posts, and the balance goes negative. Reconciliation flags that case separately as `outlay_exceeds_obligation`, without changing the journal. That keeps the journal a pure function of the ordered log: rebuilding it from the same events always gives the same result, whatever order they arrived in. An earlier draft let reconciliation decide which account a payment posted to, which made rebuilding depend on timing.

A deferred constraint trigger requires every entry to balance. Journal lines are append-only, and corrections are reversing entries.

## Reasons

- It makes the ledger credible to a finance reader at little cost.
- It gives the analyst questions with exact answers, such as unpaid obligations by agency or a trial balance.
- The journal is derived data. Because it can always be rebuilt from verified events, it doesn't need its own Merkle log. Property tests check that every entry balances and that the trial balance is zero.

## Not in scope

Full U.S. Standard General Ledger account coverage, multi-agency consolidation, and accrual schedules.
