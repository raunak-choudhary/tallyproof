# 14. Runbook

How to set up, run, reset, and debug Tallyproof on one machine, entirely from the command line. Commands appear here as they're built, and the README's status note says what works today.

## Machine setup (macOS, Apple Silicon, CLI only)

Reference machine: Apple M3, 8 GB RAM, about 45 GB free disk. The design is sized for this machine, so it should run anywhere bigger.

| Tool | Why | Install (verified 2026-10-27) | Scope |
|---|---|---|---|
| Homebrew | Package manager | already present | system |
| Colima + Docker CLI + Compose plugin | Container runtime without Docker Desktop | `brew install colima docker docker-compose` (already present on the reference machine) | system |
| OpenJDK 17 | Spark 4.2 runs on Java 17, 21, or 25 | `brew install openjdk@17` | **keg-only**: not on the system PATH, no `sudo` symlink. The Makefile sets `JAVA_HOME=$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home` for project commands only |
| Python 3.12 | Backend and data pipeline | Homebrew's `python@3.12`, which `make venv` picks automatically on macOS. Some pyenv builds lack the BLAKE2 hash module, and `make venv` refuses those with a clear message | all packages live in `backend/.venv` |
| Node 22 + pnpm | Frontend | already present | packages in `frontend/node_modules` |

A dedicated Colima profile keeps project containers separate from any other work and caps their resources:

```bash
colima start tallyproof --cpu 2 --memory 3 --disk 25   # first run creates the profile; disk grows on demand up to 25 GiB
docker context use colima-tallyproof
colima stop tallyproof                                  # when done for the day
```

## Resource budget (do not overheat the laptop)

| Workload | Limit | Rule |
|---|---|---|
| Colima VM (Redpanda and Postgres today) | 2 CPUs, 3 GiB | Per-container memory limits in `infra/compose.yaml`; Redpanda runs with `--smp 1 --memory 1G` and Postgres with 128 MB of shared buffers. Idle, the two use about 220 MB |
| Spark batch job | `local[3]`, driver memory 2 GiB, small shuffle partition count | Runs **only while the container stack is stopped** (`make data-build` checks and refuses otherwise) |
| Raw data on disk | about 4 GB of zipped archives | CSV members are extracted one at a time, converted to Parquet, then deleted; never all at once |
| Tests in CI | small committed sample (about 50k rows) | Full-size runs are local only |

## Teardown (when the project is finished)

Removes everything this project installed or created, leaving the machine as it was:

```bash
colima delete tallyproof            # VM, containers, and volumes for this project only
brew uninstall openjdk@17           # the only system package added for this project
rm -rf backend/.venv frontend/node_modules var/ data/   # local environments and downloaded data
```

Colima, Docker CLI, Python, Node, and their dependencies were already present before the project and are not removed. Any further system tool added later must be added to this table and this teardown list in the same commit.

## First run

```bash
make venv                  # backend/.venv with pinned dependencies (make doctor shows the toolchain)
make check                 # lint, strict type checks, tests
make data-fetch            # download the configured fiscal years and record their hashes
make data-build            # Spark: clean into silver and remove personal data (skips files already built)
make data-quality          # Deequ constraints on silver
make data-gold             # build ledger events with the labeled anomaly overlay (SCENARIO=smoke|demo|full|volume)
make data-sample           # refresh the committed 2,000-event sample from gold
make keygen KEY=rel        # create the release signing key in secrets/
make replay                # export the signed 2,000-event bundle to data/replay
cd frontend && pnpm install && pnpm dev   # browse and verify records locally
```

`make data-build`, `data-quality`, and `data-gold` refuse to start while a Colima VM is running, because the laptop can't hold Spark and the container stack together.

`DATA_FISCAL_YEARS` defaults to both FY2024 and FY2025. Each year is about 2 GB to download and about 20 minutes of Spark; set it to `[2025]` for a single year. Silver keeps a report per CSV file and skips any file it has already built, so adding a year doesn't redo the other one. Delete a file's report under `data/silver/_reports/` to force it.

The scenario sets the size of the gold build: `smoke` is 2,000 events with 2 of each anomaly, `demo` 20,000 with 5, `full` (the default) a million with 25, and `volume` every transaction of both years with 100.

## Run the streaming stack

```bash
cp .env.example .env       # then fill in the secret key and the four database passwords
make keygen KEY=dev        # prints the value for CHECKPOINT_PUBLIC_KEY
colima start tallyproof
make up                    # Redpanda and Postgres, then the topics; waits until both are healthy
make ps                    # containers and their health
make console               # optional broker console at http://localhost:8080
```

`make` always talks to the `colima-tallyproof` Docker context, whatever context is active. Every port binds to 127.0.0.1. The API and workers run on the host from `backend/.venv` rather than in containers, which saves the VM's memory for the broker and database.

On its first start, Postgres creates three roles from `infra/postgres/create-roles.sql`. Only those roles may connect, only the owner can create objects, and the analyst's sessions are read-only with a 3 second statement timeout. After changing a password in `.env`, run `make db-roles` to apply it. The topic script and the role script are both safe to run again.

### Workers

`make demo` starts everything in the background and `make demo-stop` stops it. To run one piece in the foreground instead, each has its own target:

| Target | What it runs |
|---|---|
| `make ingest` | Kafka consumer that appends to the ledger |
| `make checkpointer` | Signs a checkpoint every 256 leaves or 2 seconds, and timestamps it |
| `make project` | Journal, reconciliation breaks, and appended-event announcements |
| `make relay` | Publishes outbox rows to Kafka |
| `make fanout` | Forwards appended events and breaks to WebSocket clients |
| `make stream` | WebSocket endpoint on port 8001 |

### Policy corpus

The FAR text the analyst can quote lives in `backend/corpus/far/`, one JSON Lines file per part plus a manifest of text hashes. `make policy-fetch` refreshes it from the latest eCFR edition; review the diff and commit it like code. `make policy-publish` sends it to the raw topic, where each section becomes a ledger leaf. Sections whose text hasn't changed are refused as duplicates, so publishing again is safe.

## Health checks

- `GET /healthz` answers as long as the process is up.
- `GET /readyz` also checks the database and the broker, and answers 503 naming whichever one is down. Wait for it before replaying data.

## Back up the release signing key

`secrets/checkpoint_rel.key` signs the public demo bundle, and its public key is built into the web app. Keep an offline copy, for example in a password manager. If it is lost, a new key has to be generated, the bundle re-signed, and the web app rebuilt with the new public key; links to the old signatures will no longer verify.

## Stop and reset

```bash
make down                    # stop the stack, keep data
colima stop tallyproof       # free the VM's memory
make reset                   # stop, delete volumes, recreate topics and schema (asks for confirmation)
```

## Build the public demo bundle

```bash
make replay
```

This writes a signed bundle to `frontend/public/replay/`, with a manifest listing the SHA-256 of every file.

## Verify the witness data

```bash
make verify-witness
```

Checks that every witnessed checkpoint is consistent with the current log, that each external timestamp proof is valid, and that witness history hasn't been rewritten.

## Run the tamper demo locally

```bash
DEMO_TAMPER_ENABLED=true make tamper LEVEL=1 EVENT=evt_...   # edit one stored event
DEMO_TAMPER_ENABLED=true make tamper LEVEL=2 EVENT=evt_...   # also rebuild the latest checkpoint, unsigned
DEMO_TAMPER_ENABLED=true make tamper LEVEL=3 EVENT=evt_...   # and re-sign it with the local key
DEMO_TAMPER_ENABLED=true make tamper RESTORE=1               # put everything back
```

The tool refuses to run unless `DEMO_TAMPER_ENABLED` is set and the database is on loopback. It records the original rows in `var/demo/tamper-backup.json`, and refuses a second attack until the first is restored.

## Derived state

The journal and reconciliation breaks are rebuilt from the ledger, never edited.

```bash
make check-derived                     # recompute the journal and report any stored entry that differs
make rebuild-derived VIEW=journal      # clear it; the running projections rebuild it from leaf 0
make rebuild-derived VIEW=reconciliation
```

Rebuilding needs the owner role, because the derived tables are append-only to the app role. Do it after changing a reconciliation rule.

## Dead letters and control totals

```bash
make dead-letters                      # list each rejected record and why
make dead-letters EXPORT=fix.jsonl     # write the original records to a file
make dead-letters REPLAY=fix.jsonl     # publish corrected records back to the raw topic
make check-totals                      # every consumed message was appended, refused as a duplicate, or dead-lettered
```

`check-totals` reads the raw topic back and compares counts, amounts, and leaf hashes with the ledger per partition, and exits non-zero on any difference.

## Troubleshooting

| Symptom | Where to look |
|---|---|
| Consumer lag keeps growing | Consumer group lag in the broker console, `make logs SVC=ingestion`, and the dead-letter rate |
| Checkpoints aren't closing | That the checkpointer can read its key file, its logs, and the batch age setting |
| Verify fails in the browser for an untouched event | `make vectors-check` compares canonical JSON between Python and TypeScript |
| Many duplicate checks after a restart | The Bloom filter rebuild logged at partition assignment |
| The analyst refuses everything | `LLM_PROVIDER`, the daily spend cap, and query guard rejections in the logs |
| `make data-build` is slow or swapping | Stop the container stack and lower `SPARK_DRIVER_MEMORY` or `SPARK_MASTER` |
| Control totals don't match | `make check-totals` names the stage and batch that disagree |

To follow one event through the system, search the logs for its `correlation_id`.
