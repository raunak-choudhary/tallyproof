# ADR-0023: Evaluation runs are recorded as reports, in a throwaway ledger

- Status: Accepted
- Date: 2026-10-28
- Supersedes: the planned `eval_run` and `eval_result` tables and the `/api/v1/eval-runs` endpoints

## Context

Each evaluation run asks every question in a set through the real analyst and scores the answers against an independent oracle ([evaluation](../evaluation.md)). The plan stored runs as `eval_run` and `eval_result` rows in the ledger database and served them over the API for a dashboard.

A run's answers depend on the exact data the ledger holds. Running evaluations against the local stack's database would make results depend on whatever that database happened to contain, and would mix evaluation answers into the demo's data.

## Decision

Each run builds its own ledger in a throwaway Postgres container, with the production image, role script, and migrations. It loads the committed evaluation dataset and the FAR leaves, runs the journal and reconciliation projections, and signs one checkpoint with a key used only for evaluations. When the run ends, the container is discarded.

The run's record is two files written to `var/eval/<timestamp>/`: `report.json`, holding every metric and every per-question result along with the models and the commit measured, and `report.md`, the same for people. CI keeps both as artifacts. Results reach the README through a renderer that accepts only quality runs, and will reach the site as exported report files.

## Reasons

- **Reproducible.** The same commit, dataset, and recorded responses give the same report on any machine, including CI.
- **Isolated.** Evaluation answers never land in a database anyone else reads.
- **Rows would vanish.** The ledger a run uses is thrown away, so storing results in it would lose them; storing them in a second database would add a service for a few kilobytes of JSON.
- **Static is enough.** The demo site is static ([ADR-0005](0005-replay-mode-public-demo.md)); a dashboard reads exported reports as easily as an API.

## Alternatives considered

- **Evaluate against the local stack.** Rejected for non-reproducible results and data mixing.
- **`eval_run` rows in a long-lived database with an API.** Rejected: a service to keep running for data that's naturally a file.

## Consequences

- Running an evaluation needs Docker. Locally that's Colima; CI uses a machine executor.
- `var/` is gitignored, so a report that should appear on the site is exported into the replay bundle deliberately, never copied automatically.
- The analyst's own answers to readers still go in the append-only `analyst_answer` table; only evaluation results are files.
