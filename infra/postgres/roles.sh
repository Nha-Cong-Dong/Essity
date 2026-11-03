#!/bin/sh
# Creates or refreshes core_app / core_eraser (roles.sql). Used by init.sh (empty volume), by
# `just db-roles` (existing volume) and by scripts/agent_env.py. Reads the Compose variables.
# CORE_ERASER_LOGIN is optional: leave it empty in production and grant an admin by hand.
set -eu

here="$(dirname "$0")"
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname postgres \
  -v app_user="$CORE_APP_DB_USER" -v app_password="$CORE_APP_DB_PASSWORD" \
  -v refresh=1 -v eraser_login="${CORE_ERASER_LOGIN:-}" -v eraser_password="${CORE_ERASER_PASSWORD:-}" \
  -f "$here/roles.sql"
