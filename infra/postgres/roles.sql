-- Database roles for core-api (T2.22, ADR-0024). Idempotent: safe to run on every start.
--   core         owns the schema, runs migrations only (created by init.sh).
--   core_app     LOGIN, what core-api and core-worker connect as: no ownership, no DDL.
--   core_eraser  NOLOGIN, the only path that may delete a user's append-only history.
--   <eraser_login> (optional) a LOGIN that is a member of core_eraser; production grants an
--                  admin login by hand (runbook) and leaves `eraser_login` unset.
-- Run through roles.sh, which reads the variables from the environment.
-- Variables: app_user, app_password, eraser_login (may be empty), eraser_password.
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L',
              :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L',
              :'app_user', :'app_password') \gexec

SELECT 'CREATE ROLE core_eraser NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'core_eraser') \gexec

SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L',
              :'eraser_login', :'eraser_password')
WHERE :'eraser_login' <> ''
  AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'eraser_login') \gexec
SELECT format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD %L',
              :'eraser_login', :'eraser_password')
WHERE :'eraser_login' <> '' \gexec
SELECT format('GRANT core_eraser TO %I', :'eraser_login')
WHERE :'eraser_login' <> '' \gexec
