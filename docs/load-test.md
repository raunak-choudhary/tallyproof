# Load test

How fast the live pipeline goes on a laptop, where the time goes, and where it stops scaling. Every number on this page comes from one run of `make load-test` on 2026-10-30, and the command reproduces them.

## What was measured

The test starts a throwaway copy of the local stack: its own Compose project and volumes, built from the same compose file, so it has the same images and memory limits as the demo and never touches the demo ledger. It migrates the copy, runs the pipeline's real worker processes against it, and removes it afterwards. Events are real gold events, read in log order.

It measures four things:

1. **Throughput.** A backlog of 30,000 events is drained by one, two, and then three consumers (the raw topic has three partitions). The checkpointer, the projections, and the outbox relay run throughout, as they do in the demo.
2. **End-to-end latency.** 15,000 fresh events are published at a steady rate of half the measured ceiling. Each one is timed from the moment it was handed to the producer until it was appended to the log, covered by a signed checkpoint, and announced on `ledger.appended.v1`.
3. **Proof latency.** 500 inclusion proofs for random events, fetched from the API one at a time.
4. **Partition balance.** How the events spread across the raw topic's partitions.

Postgres runs inside the Colima VM, so its timestamps are moved onto the host clock using the offset measured between the two. External timestamping is switched off for the test, so it doesn't send a burst of requests to the public OpenTimestamps calendars, and the API's read rate limit is raised so the proof requests aren't throttled.

## Hardware

| | |
|---|---|
| Host | MacBook Air, Apple M3, 8 cores, 8 GiB memory, macOS 26.6 |
| VM | Colima, 2 CPUs, 3 GiB memory |
| Postgres | 16 with pgvector 0.8.7, limited to 512 MiB |
| Redpanda | 26.2.6, one broker, limited to 1,280 MiB |
| Redis | 7.4, limited to 128 MiB |
| Workers | Host processes on Python 3.12.9 |

Settings were the defaults: batches of up to 500 messages per consumer read, and a checkpoint every 256 events or 2 seconds, whichever comes first.

## Throughput and the single-writer ceiling

| Consumers | Events appended | Seconds | Events per second |
|---|---|---|---|
| 1 | 29,999 | 9.0 | 3,328 |
| 2 | 29,999 | 10.5 | 2,854 |
| 3 | 29,999 | 10.3 | 2,920 |

One event in each run was an injected duplicate, which the ledger refused.

Adding consumers doesn't help, and two are slightly slower than one. That is the design working as described in the [architecture](architecture.md#ordering): every append locks the single log-head row, so leaf indexes stay gap-free and in one global order. Extra consumers parse and validate in parallel, then queue for the same lock. On this hardware the ceiling is about 3,000 events a second.

The way past it is the one the architecture already names: one log per partition, each with its own writer, under a top-level log of shard heads. Throughput would then grow with partitions until Postgres itself is the limit.

## End-to-end latency

At a steady 1,600 events a second, with one consumer:

| From send to | p50 | p95 | p99 | Max |
|---|---|---|---|---|
| Appended to the log | 328 ms | 747 ms | 889 ms | 984 ms |
| Covered by a signed checkpoint | 409 ms | 915 ms | 1,074 ms | 1,167 ms |
| Announced by the outbox | 4,277 ms | 5,086 ms | 5,191 ms | 5,286 ms |

Most of the time to append is the consumer filling its batch: it waits for up to 500 messages or one second, whichever comes first, and at 1,600 events a second a full batch takes about a third of a second to arrive. A smaller `INGEST_MAX_BATCH` would cut latency at the cost of more transactions.

Checkpoints add about 80 ms. That is the checkpointer's 256-event trigger firing several times a second at this rate; at the demo's lower rates the 2-second timer is what closes a checkpoint instead.

Announcements are the slow part, and the relay is not the reason. Once an outbox row exists, it is published in 11 ms at the median and 37 ms at p99. The delay is before that, in the process that writes the rows. One loop runs three projections in turn (the announcements, the double-entry journal, and reconciliation), 500 events each, so announcements wait behind the other two. At this rate the loop runs about four seconds behind the log. The live WebSocket stream is fed from these announcements, so under this load it shows events about four seconds after they are appended. Proofs and verification don't wait for it: they work from the log and its checkpoints. Giving the announcement projection its own process would bring announcements close to the checkpoint time.

## Outbox lag under a backlog

The time from an outbox row being written to its being published, while consumers drained the backlog:

| Consumers | p50 | p95 | p99 | Max |
|---|---|---|---|---|
| 1 | 10 ms | 24 ms | 179 ms | 179 ms |
| 2 | 10 ms | 26 ms | 123 ms | 123 ms |
| 3 | 9 ms | 30 ms | 48 ms | 90 ms |

The relay wakes on a Postgres notification rather than polling, so its lag stays in the tens of milliseconds even under load.

## Proof latency

500 inclusion proofs against a log of 104,997 leaves:

| p50 | p95 | p99 | Max |
|---|---|---|---|
| 3 ms | 5 ms | 11 ms | 2,138 ms |

The API keeps the Merkle tree in memory and extends it as checkpoints arrive, so a proof costs one lookup and a few dozen hashes. The one slow request was a cold start: the API runs two worker processes, each builds its own tree on its first proof, and the test discards only the first request. A million leaves still fit comfortably in memory; at larger scale, proofs would be served as static tiles instead, as [the limitations page](limitations.md) describes.

## Partition balance

| Partition | Events |
|---|---|
| 0 | 35,237 |
| 1 | 34,852 |
| 2 | 34,908 |

Events are keyed by award, so one award's history stays in order on one partition. With tens of thousands of awards, no partition carries more than 34 percent of the traffic.

## Running it

```bash
make down          # the test uses the same ports as the demo stack; its data is kept
make load-test     # about ten minutes; results in var/load-test/<time>/
```

Each run writes `report.md` and `report.json`, plus every worker's log, to its own folder under `var/load-test/`. Arguments pass through `ARGS`, for example `make load-test ARGS="--events 100000 --consumers 1,3"`; `--help` lists them. The test needs the gold events from the data build (`make data-gold`).

Numbers on another machine will differ. The shape should not: throughput flat across consumers, checkpoints a fraction of a second behind the log, and announcements set by the projection loop rather than the relay.
