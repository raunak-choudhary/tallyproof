# Data profile: the FY2024 and FY2025 build

This is what happened when the full fiscal year 2024 and 2025 contract files, and the first quarter of fiscal 2024's outlay data, went through the batch pipeline on the reference laptop (Apple M3, 8 GB of memory). Every number below comes from a file the pipeline wrote during those runs, so you can reproduce it with `make data-fetch data-outlays data-build data-build-outlays data-quality data-gold`.

## Source

| File | Bytes | SHA-256 | Inside |
|---|---:|---|---|
| `FY2024_All_Contracts_Full_20261006.zip` | 2,039,742,911 | `675e42e4e67ec00574c59995f4a1ab22a377e9afd41eef3e254cc3b2cbd806e8` | 7 CSV files |
| `FY2025_All_Contracts_Full_20261006.zip` | 1,989,294,113 | `294f767c2021b81dec09ab0ea6ee0c5f076588cb6963101ec45d93d59ba8bf60` | 7 CSV files, 14.3 GB uncompressed |
| `FY2024P01-P03_All_TAS_AccountBreakdownByAward_...zip` (outlays) | 1,041,002,352 | recorded in the manifest | 8 CSV files, 10.8 GB uncompressed |

The contract files come from the USAspending award data archive. The outlay file is generated on request by the USAspending download API, one quarter at a time, because a whole fiscal year is more than the server will build. It splits its rows into grant, contract, and unlinked files, and only the three contract files (2.85 GB) are read.

The archive server drops long downloads every hundred megabytes or so. The downloader resumes where it stopped; the FY2024 contract file took ten resumes.

The download manifest (`data/bronze/manifest.jsonl`) records the URL, size, and hash. A file already on disk is reused only if its hash matches the manifest; otherwise it is downloaded again, and a download that ends short of the advertised size fails.

## Bronze to silver

Each CSV is read once, typed against an explicit schema, cut down to an allowlist of 36 columns, and written as Parquet. The CSV is deleted as soon as its Parquet is written, so the disk never holds the whole year uncompressed.

FY2025:

| File | Rows read | Rows kept | Sole proprietors removed |
|---|---:|---:|---:|
| 1 | 1,000,000 | 983,440 | 16,560 |
| 2 | 1,000,000 | 983,292 | 16,708 |
| 3 | 1,000,000 | 981,454 | 18,546 |
| 4 | 1,000,000 | 984,739 | 15,261 |
| 5 | 1,000,000 | 985,869 | 14,131 |
| 6 | 1,000,000 | 986,405 | 13,595 |
| 7 | 639,396 | 629,213 | 10,183 |
| **Total** | **6,639,396** | **6,534,412** | **104,984** |

FY2024:

| File | Rows read | Rows kept | Sole proprietors removed |
|---|---:|---:|---:|
| 1 | 1,000,000 | 984,227 | 15,773 |
| 2 | 1,000,000 | 982,575 | 17,425 |
| 3 | 1,000,000 | 983,040 | 16,960 |
| 4 | 1,000,000 | 984,719 | 15,281 |
| 5 | 1,000,000 | 986,303 | 13,697 |
| 6 | 1,000,000 | 986,554 | 13,446 |
| 7 | 692,800 | 682,615 | 10,185 |
| **Total** | **6,692,800** | **6,590,033** | **102,767** |

Across both years, 13,332,196 transactions were read and 13,124,445 kept.

About 1.6 percent of rows describe awards to sole proprietorships, where the recipient's name is usually a person's name. Those rows are dropped entirely rather than masked. The columns that could identify a person (names, addresses, phone numbers) were never in the allowlist to begin with.

No rows were quarantined. An earlier run quarantined almost a million rows because two report timestamps carry a `+00` offset the schema didn't expect; that was a schema bug, fixed by reading those columns as UTC wall-clock times, and the quarantine count is now zero.

The silver Parquet is 581 MB for FY2025 and 601 MB for FY2024. FY2025 took 20.8 minutes on its first run; FY2024, after a change to parse each CSV once instead of once per output, took 18.9 minutes with the Python driver at 90 MB. Silver skips files it has already built, so adding FY2024 didn't redo FY2025.

## Outlays

The outlay file reports, for each award, Treasury account, program activity, object class, and month, how much has been paid since the start of the fiscal year. The outlay job keeps contract awards, adds the rows up to one cumulative figure per award, account, and month, and takes the change from the previous month as that month's payment.

| | Rows |
|---|---:|
| Read from the three contract files | 2,188,954 |
| Contract award rows | 2,173,974 |
| Monthly payments written | 1,084,223 |
| No outlay figure (rows that report only obligations) | 687,550 |
| No change from the previous month | 282,846 |
| Cumulative figure went down, quarantined | 3,515 |

It took 82 seconds and wrote 19 MB of Parquet.

## Quality checks

Deequ ran 11 checks over all 13.1 million silver rows of both years in 30 seconds. Every check scored 1.0.

| Level | Check |
|---|---|
| Error | Transaction key present and unique |
| Error | Award key, recipient UEI, and action date present |
| Error | Fiscal year is one of the configured years |
| Error | Action date falls inside the configured fiscal years |
| Error | Obligation amount under one trillion dollars in absolute value |
| Warning | Obligation amount present |
| Warning | Recipient UEI matches the 12-character format |
| Warning | Awarding agency present |

An error-level failure stops the build; a warning is reported and the build continues.

## Gold

The gold step takes the first one million transactions by action date (with both years loaded, October 2023 to mid-January 2024), conforms them into ledger events sorted by arrival time, adds an outlay event for every month each of those awards was paid in, and adds a labeled overlay of known anomalies so the evaluations have exact ground truth.

| | |
|---|---:|
| Contract events | 1,000,000 |
| Outlay events for those awards | 704,400 |
| Injected events | 375 |
| Invalid records | 25 |
| Rows rejected while conforming | 0 |
| Time | 3.5 minutes |
| Peak memory of the Python process | 459 MB |

The overlay adds 25 of each of nine anomaly types: duplicate deliveries, semantic duplicates of an award, late arrivals, descriptions containing prompt-injection text, de-obligations larger than the award, outlays on awards that were never obligated, outlays above the award's obligations, bursts of small awards to one recipient (eight events each), and records that fail the schema. Labels live in a separate file. Nothing inside an event says it was injected.

A contract event is stamped with when the transaction was first reported. The first FY2024 build used the last edit time instead, and since these records are edited for years, 764,421 of the million looked reported long after the fact. An outlay event is stamped with when the agency's report was last modified, and the month it covers is in the payload.

## Reconciliation on the replayed stream

Running the reconciliation rules over the 1,704,750 events that would reach the ledger (duplicates removed, as ingestion does) took 48 seconds:

| Break | Count | Injected and caught |
|---|---:|---:|
| `outlay_exceeds_obligation` | 68,425 | 25 of 25 |
| `late_after_close` | 61,508 | 25 of 25 |
| `possible_duplicate_award` | 59,331 | 25 of 25 |
| `deobligation_exceeds_award` | 28,409 | 25 of 25 |
| `orphan_outlay` | 410 | 25 of 25 |

Every injected anomaly is caught. Most of the real breaks come from the slice rather than from the government's books. An award made before October 2023 has a modification or an outlay in the slice but not the obligation that preceded it, so its outlays exceed what the ledger has seen and its de-obligations take it below zero. The duplicate rule (same recipient, amount, and date under a different award) is also broad: agencies routinely issue several identical orders on one day. These counts are reported as they are, and tuning the rules against the labels is part of the evaluation work.

## What feeds the live pipeline

The replay producer streams these gold events into Kafka in arrival order, keyed by award. In a local run on the same laptop it published 20,000 events in 4.0 seconds using 72 MB of memory, and the ledger accepted every one with gap-free leaf indexes. Publishing the same 20,000 again added nothing: all 20,000 were recorded as duplicates.
