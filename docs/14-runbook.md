# 14. Runbook

> Commands become real as tasks land; each section notes the task that delivers it.

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
