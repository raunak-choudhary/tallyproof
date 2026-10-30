# ADR-0025: Recipient bursts with Count-Min Sketches

- Status: Accepted
- Date: 2026-10-30

## Context

The anomaly overlay injects 25 recipient bursts into the full gold build: eight new awards to one recipient, five minutes apart. No rule detected them. Measuring real traffic first showed why a simple rule would be useless:

| Rule tried on the full gold build | Bursts caught | Windows of real traffic flagged |
|---|---|---|
| 8 or more new awards to one recipient in an hour | 25 of 25 | about 24,700 |
| The same, counting only distinct arrival times | 25 of 25 | about 15,400 |
| The same, for a recipient with few awards in the previous 30 days | 2 of 25 | a few hundred |

Large contractors routinely get dozens of awards an hour, and the overlay had placed its bursts on such vendors, so the bursts looked like their normal traffic.

## Decision

1. **Inject bursts the way they matter.** Each injected burst now goes to a brand-new recipient: a fresh 12-character Unique Entity ID, with awards copied from a real one. A run of awards to a vendor with no history is the pattern of a contract split to stay under a review threshold.
2. **Detect a burst relative to the recipient's history.** A `recipient_burst` break is raised for at least eight new awards to one recipient within an hour, when that recipient had no awards on any of the 30 days before (`tallyproof_core/bursts.py`).
3. **Count with Count-Min Sketches, so memory doesn't grow with recipients.**
   - Four sets of one-hour windows, offset by 15 minutes, each with a 4,096 by 4 sketch. Any burst spanning at most 45 minutes fits wholly inside one window.
   - When a recipient's estimate reaches eight, the count is confirmed exactly from a two-hour buffer of recent awards, so a sketch collision can never raise a break.
   - One 65,536 by 4 sketch per day for the last 30 days answers "any awards recently?". Sketches only overcount, so a collision can hide a burst but never invent one. With ε = e / width and δ = e^-depth, a day with 10,000 recipients hides one in about 2,000 checks.
4. **Score every rule against gold.** `make recon-report` streams the gold build through the reconciliation engine and reports, for each labelled anomaly, how many its rule caught, plus the breaks no label explains.

## Results

On the full gold build (1,704,750 events after duplicates are refused): every rule catches 25 of 25, recipient bursts included, in about 3.5 minutes. The burst rule also flags 216 bursts in real traffic, recipients with no awards in a month that then got eight or more in an hour. Those aren't errors in the rule; they are the cases it exists to surface, and they are reported as findings to review, not counted against it. The committed evaluation dataset still holds its three older bursts, and the rule catches all three.

## Consequences

- The gold build had to be rebuilt. The committed evaluation dataset and the replay bundle were not, so recorded model answers and the witnessed checkpoint stay valid.
- A burst to an established vendor is not flagged. Catching that would need a per-recipient rate model, a heavier piece of work with its own false alarms.
