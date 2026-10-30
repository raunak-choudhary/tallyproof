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

The figures for the full gold build and for silver come from the final measured run and are added to this page then.
