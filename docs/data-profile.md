# Data profile: the FY2025 contracts build

This is what happened when the full fiscal year 2025 contract file went through the batch pipeline on the reference laptop (Apple M3, 8 GB of memory). Every number below comes from a file the pipeline wrote during that run, so you can reproduce it with `make data-fetch data-build data-quality data-gold`.

## Source

| | |
|---|---|
| File | `FY2025_All_Contracts_Full_20261006.zip` from the USAspending award data archive |
| Downloaded | 1,989,294,113 bytes |
| SHA-256 | `294f767c2021b81dec09ab0ea6ee0c5f076588cb6963101ec45d93d59ba8bf60` |
| Inside | 7 CSV files, 14.3 GB uncompressed |

The download manifest (`data/bronze/manifest.jsonl`) records the URL, size, and hash. A file already on disk is reused only if its hash matches the manifest; otherwise it is downloaded again, and a download that ends short of the advertised size fails.

## Bronze to silver

Each CSV is read once, typed against an explicit schema, cut down to an allowlist of 36 columns, and written as Parquet. The CSV is deleted as soon as its Parquet is written, so the disk never holds the whole year uncompressed.

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

About 1.6 percent of rows describe awards to sole proprietorships, where the recipient's name is usually a person's name. Those rows are dropped entirely rather than masked. The columns that could identify a person (names, addresses, phone numbers) were never in the allowlist to begin with.

No rows were quarantined. An earlier run quarantined almost a million rows because two report timestamps carry a `+00` offset the schema didn't expect; that was a schema bug, fixed by reading those columns as UTC wall-clock times, and the quarantine count is now zero.

The silver Parquet for the year is 582 MB. The silver step took 20.8 minutes on the first full run. It was then changed to parse each CSV once instead of once per output, and hasn't been re-timed at full size since, so treat 20.8 minutes as an upper bound.

## Quality checks

Deequ ran 11 checks over all 6.5 million silver rows in 23 seconds. Every check scored 1.0.

| Level | Check |
|---|---|
| Error | Transaction key present and unique |
| Error | Award key, recipient UEI, and action date present |
| Error | Fiscal year is one of the configured years |
| Error | Action date falls inside fiscal year 2025 |
| Error | Obligation amount under one trillion dollars in absolute value |
| Warning | Obligation amount present |
| Warning | Recipient UEI matches the 12-character format |
| Warning | Awarding agency present |

An error-level failure stops the build; a warning is reported and the build continues.

## Gold

The gold step takes the first one million transactions by action date, conforms them into ledger events sorted by arrival time, and adds a labeled overlay of known anomalies so the evaluations have exact ground truth.

| | |
|---|---:|
| Real events | 1,000,000 |
| Injected events | 125 |
| Invalid records | 25 |
| Rows rejected while conforming | 0 |
| Time | 3.2 minutes |
| Peak memory of the Python process | 363 MB |

The overlay adds 25 of each of six anomaly types: duplicate deliveries, semantic duplicates of an award, late arrivals, descriptions containing prompt-injection text, de-obligations larger than the award, and records that fail the schema. Labels live in a separate file. Nothing inside an event says it was injected.

## What feeds the live pipeline

The replay producer streams these gold events into Kafka in arrival order, keyed by award. In a local run on the same laptop it published 20,000 events in 4.0 seconds using 72 MB of memory, and the ledger accepted every one with gap-free leaf indexes. Publishing the same 20,000 again added nothing: all 20,000 were recorded as duplicates.
