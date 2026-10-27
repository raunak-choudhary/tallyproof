# 14. Runbook

> Commands become real as tasks land; each section notes the task that delivers it. Everything is done from the command line. No Docker Desktop and no GUI tools.

## Machine setup (macOS, Apple Silicon, CLI only)

Reference machine: Apple M3, 8 GB RAM, about 45 GB free disk. The design is sized for this machine, so it should run anywhere bigger.

| Tool | Why | Install (verified 2026-10-27) | Scope |
|---|---|---|---|
| Homebrew | Package manager | already present | system |
| Colima + Docker CLI + Compose plugin | Container runtime without Docker Desktop | `brew install colima docker docker-compose` (already present on the reference machine) | system |
| OpenJDK 17 | Spark 4.2 runs on Java 17, 21, or 25 | `brew install openjdk@17` | **keg-only**: not on the system PATH, no `sudo` symlink. The Makefile sets `JAVA_HOME=$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home` for project commands only |
| Python 3.12 | Backend and data pipeline | already present | all packages live in `backend/.venv` |
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

## Run (T-104 onward)

```bash
cp .env.example .env           # then fill secrets; never commit .env
make keygen                    # prints an Ed25519 key pair; paste into .env
make up                        # Redpanda, Console, Postgres, Redis, API, workers, web
make seed SCENARIO=demo        # generate and produce a seeded scenario
open http://localhost:3000     # web; Console at :8080; API docs at :8000/api/v1/docs/
```

## Health

- `GET /healthz`: process is alive.
- `GET /readyz`: broker, database, cache reachable. Use before running seeds.

## Reset

```bash
make down          # stop
make reset         # stop, drop volumes, recreate topics and schema (destructive, asks to confirm)
```

## Replay bundle (E-506)

```bash
make seed SCENARIO=demo && make eval SET=full MODE=cached && make replay
# writes frontend/public/replay/ with manifest.json listing SHA-256 of every file
```

## Verify the witness (T-207)

```bash
make verify-witness    # every committed checkpoint must be consistent with the live log
```

## Tamper demo (T-208, local only)

```bash
DEMO_TAMPER_ENABLED=true make tamper LEVEL=1 EVENT=evt_...
```

## Debug

| Symptom | Check |
|---|---|
| Consumer lag growing | Redpanda Console group lag; `make logs SVC=ingestion`; DLQ rate |
| Checkpoints not closing | `CHECKPOINT_SIGNING_KEY` set? checkpointer logs; batch age config |
| Verify fails in browser for untampered event | Run `make vectors-check` (cross-language canonical JSON) |
| Fast-path unique violations > 0 | Bloom state stale; check rebuild logs on startup |
| Analyst refuses everything | `LLM_PROVIDER`, budget cap, guard rejections in logs |
| Control totals mismatch | `make check-totals` output names the stage and batch |

Tracing one event: search logs for its `correlation_id`.
