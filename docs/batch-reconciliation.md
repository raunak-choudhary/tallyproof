# Batch reconciliation in DuckDB

The reconciliation rules run in two ways. The streaming engine reads one event at a time in log order and keeps running state, so a break is known the moment its event arrives. The same rules also exist as set-based SQL in DuckDB, run over a whole history at once (`backend/tallyproof_pipeline/batch_recon.py`). Running both over the same events checks one against the other; running the SQL over the cleaned transactions shows what the batch path costs at full size.

```bash
make batch-recon
```

It loads the gold events into DuckDB, runs every rule in SQL, runs the streaming engine over the same events, and compares the breaks rule by rule. Then it runs the rules that apply to raw transactions over the 13.1 million rows in silver. DuckDB is held to two threads and 2 GB, spilling to disk past that, so the laptop stays usable. The report goes to `data/batch_recon.json`.

## How each rule reads in SQL

| Rule | In SQL |
|---|---|
| Possible duplicate award | The first new award for each recipient, amount, and action date; later awards with that signature and a different award key |
| De-obligation exceeds award | A running sum of an award's obligations in log order, below zero after a negative adjustment |
| Orphan outlay | An outlay that is the first event the log has for its award |
| Outlay exceeds obligation | Running sums of obligations and of each Treasury account's change in cumulative outlays, compared after each outlay |
| Late arrival | Arrival more than 72 hours after the event |
| Recipient burst | Eight or more new awards to a recipient within any 60 minutes, after 30 days with none |

## Where they agree

On the committed evaluation dataset, every rule finds exactly the same breaks both ways: nothing only one side found. A unit test holds that, rule by rule, so the two can't drift apart.

## Where they differ, by design

- **Windows.** The streaming burst rule counts in fixed one-hour windows, four sets offset by 15 minutes, with sketches ([ADR-0025](adr/0025-recipient-bursts-with-count-min-sketches.md)). The SQL counts over a sliding hour exactly. A burst spread over 46 to 60 minutes is caught by the SQL and can be missed by the stream; any burst within 45 minutes is caught by both.
- **What "earlier" means.** The stream knows only what has arrived; the SQL sees every event, but each rule orders by log position, so it reproduces the stream's view rather than hindsight.
- **Raw transactions.** In silver there are no events, so only the rules that apply to transactions run there: duplicates, de-obligations below zero, and bursts, timed by each transaction's first report.

## Measured on the full build

One run of `make batch-recon` on 31 October 2026, on the laptop in the [load test](load-test.md#hardware), with DuckDB held to two threads and 2 GB.

Over the gold build's 1,704,750 events (after duplicates are refused), the SQL took 11 seconds for every rule together, and the streaming engine took 215 seconds for the same events.

| Rule | SQL | Stream | Both | Only SQL | Only stream |
|---|---|---|---|---|---|
| Possible duplicate award | 59,331 | 59,331 | 59,331 | 0 | 0 |
| De-obligation exceeds award | 28,409 | 28,409 | 28,409 | 0 | 0 |
| Orphan outlay | 410 | 410 | 410 | 0 | 0 |
| Outlay exceeds obligation | 68,425 | 68,425 | 68,425 | 0 | 0 |
| Late arrival | 61,507 | 61,508 | 61,507 | 0 | 1 |
| Recipient burst | 255 | 241 | 152 | 103 | 89 |

Four rules agree break for break. Late arrivals differ by one event the stream flags and the SQL doesn't; it hasn't been traced, and both use the same 72-hour cut-off, so the likeliest cause is how one timestamp is parsed. Bursts are compared by the event that raised them, which is where the two windows differ most: the SQL raises a burst on the eighth award in any sliding hour, the stream on the award that brings a fixed window to eight, and a burst found by both can be credited to different events. The SQL also catches bursts spread over more than 45 minutes, which the stream's windows can miss, as described above.

Over the 13,124,445 transactions in silver:

| Rule | Breaks | Seconds |
|---|---|---|
| Possible duplicate award | 842,615 | 14.1 |
| De-obligation below zero | 216,901 | 5.8 |
| Recipient burst | 419 | 137.9 |

The duplicate count is high because the rule only flags a possible duplicate: on real data, many awards share a recipient, an amount, and a date for ordinary reasons, so each is a lead to check, not a finding. The burst rule is the slow one, since every crossing looks back over the recipient's previous 30 days.
