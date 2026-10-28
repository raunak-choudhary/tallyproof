#!/usr/bin/env bash
# Runs once, when the Postgres container initializes an empty data directory.
set -euo pipefail
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v owner_password="$DB_OWNER_PASSWORD" \
  -v app_password="$DB_APP_PASSWORD" \
  -v analyst_password="$DB_ANALYST_PASSWORD" \
  -f /infra/create-roles.sql
