#!/usr/bin/env bash
# One command from a fresh clone to a verified live event. Run it through `make demo`.
#
# Starts Redpanda and Postgres on the Colima profile, migrates, starts the API,
# the ingestion consumer, and the checkpointer as background processes, streams
# real gold events (or the committed sample if no gold build exists), waits for
# a checkpoint to cover them, and verifies one event from the API against the
# pinned key. `make demo-stop` stops everything.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUN="$ROOT/var/demo"
PY="$ROOT/backend/.venv/bin/python"
EVENTS=${DEMO_EVENTS:-20000}
API=http://127.0.0.1:8000
export DJANGO_SETTINGS_MODULE=config.settings.local
mkdir -p "$RUN"

step() { printf '\n== %s\n' "$1"; }

start() {  # name, command...
  local name=$1; shift
  if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then
    echo "$name already running"
    return
  fi
  # exec, so the recorded PID is the service itself and not a wrapper shell.
  (cd "$ROOT/backend" && exec nohup "$@" >"$RUN/$name.log" 2>&1 </dev/null) &
  echo $! >"$RUN/$name.pid"
  echo "$name started, log in var/demo/$name.log"
}

step "Containers"
if ! colima status tallyproof >/dev/null 2>&1; then
  colima start tallyproof --cpu 2 --memory 3 --disk 25
fi
make -C "$ROOT" --no-print-directory up

step "Schema"
make -C "$ROOT" --no-print-directory migrate

step "Services"
start api "$ROOT/backend/.venv/bin/gunicorn" config.wsgi --workers 2 --bind 127.0.0.1:8000
start ingest "$PY" manage.py ingest
start checkpointer "$PY" manage.py checkpointer
for _ in $(seq 1 30); do
  curl -fs "$API/readyz" >/dev/null && break
  sleep 1
done
curl -fs "$API/readyz" >/dev/null || { echo "the API never became ready; see var/demo/api.log"; exit 1; }
echo "API ready at $API"

step "Streaming $EVENTS real events"
if [ -f "$ROOT/data/gold/events.jsonl.gz" ]; then
  make -C "$ROOT" --no-print-directory data-replay LIMIT="$EVENTS" RATE=5000
else
  echo "No gold build found; streaming the committed 2,000-event sample instead."
  make -C "$ROOT" --no-print-directory data-replay \
    EVENTS_FILE="$ROOT/testdata/sample/gold_events_sample.jsonl.gz" RATE=5000
fi

step "Waiting for a checkpoint to cover the log"
previous=-1
for _ in $(seq 1 60); do
  size=$(curl -fs "$API/api/v1/checkpoints/latest" | "$PY" -c "import json,sys; print(json.load(sys.stdin)['tree_size'])" 2>/dev/null || echo 0)
  if [ "$size" -gt 0 ] && [ "$size" = "$previous" ]; then break; fi
  previous=$size
  sleep 2
done
echo "latest signed checkpoint covers $size events"

step "Verifying a random event against the pinned key"
(cd "$ROOT/backend" && "$PY" manage.py verify_event --api "$API")

cat <<DONE

The live ledger is running.
  API docs:        $API/api/v1/docs/
  Latest checkpoint: $API/api/v1/checkpoints/latest
  Verify another:  make verify-event
  Live web page:   make web-live   (then open http://localhost:3000)
  Stop everything: make demo-stop
DONE
