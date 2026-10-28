#!/usr/bin/env bash
# Create the ledger's topics if they don't exist yet. Safe to run repeatedly.
set -euo pipefail

create() {
  local topic=$1 partitions=$2
  shift 2
  if rpk topic describe "$topic" >/dev/null 2>&1; then
    echo "exists: $topic"
  else
    rpk topic create "$topic" --partitions "$partitions" --replicas 1 "$@"
  fi
}

# Raw events are keyed by award, so one award's history stays in order.
create "$KAFKA_TOPIC_EVENTS_RAW" 3 -c retention.ms=-1
# Records that failed validation, kept for inspection.
create "$KAFKA_TOPIC_EVENTS_DLQ" 1 -c retention.ms=-1
