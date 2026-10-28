# Real-data sample

`gold_events_sample.jsonl.gz` holds the first 2,000 ledger events produced from
USAspending.gov FY2025 contract transactions, after cleaning removed personal data.
CI uses it to test the pipeline end to end on real records without downloading
the full archive. Regenerate it with `make data-sample` after a gold build.
