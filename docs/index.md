# Tallyproof

Tallyproof is a streaming ledger for public spending data with an AI analyst on top. Every number the analyst gives you comes from a query over the ledger, and every claim links to the source record with a cryptographic proof that the record hasn't changed since it arrived. You can check that proof in your own browser.

These pages are the project's documentation. The code is on [GitHub](https://github.com/raunak-choudhary/tallyproof), and the [demo](https://raunak-choudhary.github.io/tallyproof/) is a static replay of 2,000 real FY2025 contract records that you can verify and tamper with yourself.

## Where to start

| If you want to know | Read |
|---|---|
| What it does, in a 25 second demo and a one minute architecture walk-through | [Videos and diagrams](media.md) |
| How records become proofs, and how tampering is caught | [Architecture](architecture.md) |
| Schemas, Kafka topics, database, and API | [Backend design](backend-design.md) |
| How answer quality is measured | [Evaluation](evaluation.md) |
| What was scaled down for one laptop and free tiers | [Limitations](limitations.md) |
| What the full FY2025 build produced | [Data profile](data-profile.md) |
| What is protected, from whom, and how | [Threat model](threat-model.md) |
| How it's tested | [Testing](testing.md) |
| How to run, reset, and debug it | [Runbook](runbook.md) |
| Every setting | [Configuration](configuration.md) |
| Which technologies, at which versions, and why | [Technology choices](tech-stack.md) |
| How it would map to AWS | [AWS reference architecture](aws-reference-architecture.md) |
| Why each major decision went the way it did | [Decisions](adr/README.md) |
| The functions behind proofs and answers | [Core library](reference/core.md) and [Analyst](reference/analyst.md) |
| Where every outside claim comes from | [Sources](references.md) |
