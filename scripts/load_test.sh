#!/usr/bin/env bash
# Load test on a throwaway copy of the local stack. Run it through `make load-test`.
#
# The copy is its own Compose project with its own volumes, built from the same
# compose file, so it has the same images and memory limits as the demo stack and
# never touches the demo ledger. It binds the same loopback ports, so the demo
# stack has to be stopped first (`make down` keeps its data). Whatever happens,
# the copy and its volumes are removed at the end. Results land in var/load-test/.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PROFILE=${COLIMA_PROFILE:-tallyproof}
PROJECT=tallyproof-load
DOCKER=(docker --context "colima-$PROFILE")
COMPOSE=("${DOCKER[@]}" compose --env-file "$ROOT/.env" -f "$ROOT/infra/compose.yaml" -p "$PROJECT")

if [ -n "$("${DOCKER[@]}" ps -q --filter label=com.docker.compose.project=tallyproof)" ]; then
  echo "The demo stack is running and holds the same ports. Stop it with 'make down' (its data is kept)."
  exit 1
fi

cleanup() {
  echo "Removing the throwaway stack"
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== Starting a throwaway stack ($PROJECT)"
"${COMPOSE[@]}" up -d --wait redpanda postgres redis
"${COMPOSE[@]}" run --rm topics
make -C "$ROOT" --no-print-directory migrate

echo "== Measuring"
cd "$ROOT/backend"
COLIMA_PROFILE=$PROFILE LOAD_TEST_PROJECT=$PROJECT \
  .venv/bin/python -m tallyproof_pipeline.load_test "$@"
