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
| Colima VM (Redpanda, Postgres, Redis, object store) | 2 CPUs, 3 GiB | Per-container memory limits in `compose.yaml`; Redpanda runs with `--smp 1 --memory 1G` |
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

Working today:

```bash
make venv                  # backend/.venv with pinned dependencies (make doctor shows the toolchain)
make check                 # lint, strict type checks, tests
make data-fetch            # download the configured fiscal years and record their hashes
make data-build            # Spark: clean into silver and remove personal data
make data-quality          # Deequ constraints on silver
make data-gold             # build ledger events with the labeled anomaly overlay
make data-sample           # refresh the committed 2,000-event sample from gold
make keygen KEY=rel        # create the release signing key in secrets/
make replay                # export the signed 2,000-event bundle to data/replay
cd frontend && pnpm install && pnpm dev   # browse and verify records locally
```

`make data-build`, `data-quality`, and `data-gold` refuse to start while a Colima VM is running, because the laptop can't hold Spark and the container stack together.

Coming with the streaming ledger:

```bash
cp .env.example .env
colima start tallyproof
make up                    # Redpanda, Postgres, Redis, object storage, API, workers, web
make data-replay           # stream gold events into Kafka
```

## Health checks

- `GET /healthz` answers as long as the process is up.
- `GET /readyz` also checks the broker, the database, and the cache. Wait for it before replaying data.

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
DEMO_TAMPER_ENABLED=true make tamper LEVEL=1 EVENT=evt_...
```

The tool refuses to run unless the settings are local and the database is on loopback.

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
