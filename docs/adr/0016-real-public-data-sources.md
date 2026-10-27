# ADR-0016: Real public spending data with a labeled synthetic overlay

- Status: Accepted
- Date: 2026-10-27

## Context

The first plan used only a synthetic generator. For reviewers who build data pipelines, all-synthetic data is the weakest part of the project: it says nothing about acquiring, cleaning, profiling, and validating messy real data at volume. The goal is real finance data at gigabyte scale (10 to 100 GB, not terabytes), taken from official APIs and bulk files rather than scraped, with no personal data.

## Decision

### Sources (all official, keyless, verified 2026-10-27)

| Role | Source | Access | Measured size |
|---|---|---|---|
| Main dataset | USAspending.gov contract transactions, Award Data Archive | `files.usaspending.gov/award_data_archive/FY<year>_All_Contracts_Full_<date>.zip`, listed by `POST /api/v2/bulk_download/list_monthly_files/`. API docs: "Endpoints do not currently require any authorization." | FY2024: 1.90 GB zipped, 13.8 GB CSV in 7 members. FY2025: 1.85 GB zipped, 13.3 GB CSV |
| Payments (outlays) | USAspending account-level "Account Breakdown by Award" (`POST /api/v2/download/accounts/`, `submission_types: ["award_financial"]`) | Generated download, keyless | FY2025 Q1 alone: 5.9 million rows |
| Live feed | Treasury Fiscal Data, Daily Treasury Statement, deposits and withdrawals of operating cash (`/v1/accounting/dts/deposits_withdrawals_operating_cash`) | Keyless; documented as "offered free, without restriction" | Small; one set of rows per business day |
| Policy corpus | Federal Acquisition Regulation (FAR) | Public U.S. government text | Small |
| Ground truth for anomaly evals | Seeded synthetic overlay injected into the real event stream | n/a | n/a |

**Volume target:** FY2025 first (about 13 GB of CSV), then FY2024 for about 27 GB in total, inside the project's 10 to 100 GB target and within the reference laptop's 45 GB of free disk (ADR-0017 explains the out-of-core processing).

### Outlay data (verified 2026-10-27)

A real FY2025 Q1 download was generated and its header read. Each row carries `transaction_obligated_amount`, `gross_outlay_amount_FYB_to_period_end`, and the award keys `award_unique_key` and `award_id_piid`, which also appear in the contract transaction files, so outlays join to obligations per award. Outlay amounts are cumulative from the start of the fiscal year, so the per-period payment is the difference between consecutive periods for the same award and account. The silver job computes that difference and quarantines rows where it goes negative without a matching correction.

### Medallion layers

1. **Bronze:** original zips, untouched, with a manifest (URL, size, SHA-256, fetch time). The file hashes are appended to the Merkle log as source-file leaves, so provenance reaches back to the exact file the government published.
2. **Silver:** Spark job, one CSV member at a time: types, deduplication, normalization, personal data removal (see the [threat model](../threat-model.md)), and a quarantine table with reason codes. Deequ constraints gate the build.
3. **Gold:** conformed ledger events in event-time order.
4. **Lake:** silver and gold as Parquet (Iceberg tables later). This holds everything.
5. **Ledger:** a replayed slice of gold events (default 1M, configurable) streams through Kafka into the verifiable ledger. The README states plainly that the lake holds the full dataset and the Merkle ledger holds the replayed stream, which is how lakes and transactional stores divide work in practice.

### Domain mapping

| Finance operations concept | Federal spending equivalent | Event type |
|---|---|---|
| Purchase order / commitment | Contract obligation (new award or modification with positive amount) | `obligation.recorded` |
| Credit / reversal | De-obligation (negative modification) | `obligation.adjusted` |
| Payment | Outlay reported against the award | `outlay.reported` |
| Bank cash movement | Treasury deposit or withdrawal | `cash.movement` |
| Vendor | Recipient (business entities only) | `account_id` = recipient UEI |

Reconciliation compares outlays with obligations per award (outlays exceeding obligations, outlays with no award, de-obligations exceeding the award). The journal (ADR-0013) uses simplified budgetary entries in place of AR and AP.

### Ground truth

- Factual questions about real data ("total obligated by agency X to recipient Y in FY2025") have exact answers computed by the eval oracle from silver data.
- Anomaly evals use the seeded overlay, whose labels live only in the manifest. Naturally occurring anomalies in the real data are labeled by documented deterministic rules and reported separately, never mixed with injected labels.

## Consequences

- The project's data rule is now: no personal data, and real data only from public official sources, plus a labeled synthetic overlay.
- The synthetic generator becomes an overlay injector.
- CI uses a committed sample of about 50k PII-free real rows; full-size builds are local and their profiling reports are committed as evidence.
- Source data quality is the government's. The profiling report documents known issues rather than hiding them.
