#!/bin/sh
# Runs once, on an empty data volume. One database and one login role per service (ADR-0007):
# each role owns its own database and cannot connect to the other one.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v core_user="$CORE_DB_USER" -v core_password="$CORE_DB_PASSWORD" -v core_db="$CORE_DB_NAME" \
  -v core_test_db="${CORE_DB_NAME}_test" \
  -v ai_user="$AI_DB_USER" -v ai_password="$AI_DB_PASSWORD" -v ai_db="$AI_DB_NAME" <<'SQL'
CREATE ROLE :"core_user" LOGIN PASSWORD :'core_password';
CREATE ROLE :"ai_user" LOGIN PASSWORD :'ai_password';

CREATE DATABASE :"core_db" OWNER :"core_user";
CREATE DATABASE :"ai_db" OWNER :"ai_user";
-- Separate database for core-api's tests, so running them never touches local data.
CREATE DATABASE :"core_test_db" OWNER :"core_user";

-- PUBLIC gets CONNECT on new databases by default; only the owner should.
REVOKE ALL ON DATABASE :"core_db" FROM PUBLIC;
REVOKE ALL ON DATABASE :"ai_db" FROM PUBLIC;
REVOKE ALL ON DATABASE :"core_test_db" FROM PUBLIC;
SQL
