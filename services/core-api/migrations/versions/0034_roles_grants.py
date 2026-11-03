"""roles_grants

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-03 10:00:00.000000

T2.22 (ADR-0024): three database roles. The owner `core` only runs migrations; `core_app` is what
core-api and core-worker log in as (CRUD on tables, no ownership, so no `ALTER TABLE ... DISABLE
TRIGGER`); `core_eraser` is the one way to delete a user's history. The roles themselves belong to
the cluster and are made by infra/postgres/roles.sql (`just db-roles`): `core` is not a superuser
and cannot make them, so this migration fails loudly when they are missing instead of skipping the
grants.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out, not imported: a later change must not change what this ran.
GRANTS = """
DO $grants$
BEGIN
  IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('core_app', 'core_eraser')) < 2 THEN
    RAISE EXCEPTION 'roles core_app and core_eraser are missing: run `just db-roles` first'
      USING ERRCODE = 'undefined_object';
  END IF;
  -- The database and the owner come from where the migration runs: the same file serves
  -- core, core_test, a lane's database and production.
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO core_app, core_eraser', current_database());
  GRANT USAGE ON SCHEMA public TO core_app, core_eraser;
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO core_app;
  REVOKE ALL ON TABLE public.alembic_version FROM core_app;
  GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO core_app;
  -- Tables and sequences made by later migrations (M7-M9 and on) reach core_app by themselves.
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public'
    ' GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO core_app', current_user);
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public'
    ' GRANT USAGE, SELECT ON SEQUENCES TO core_app', current_user);
  -- The cascade of DELETE FROM "user" runs with the owner's rights; the eraser needs only the
  -- user table itself (and SELECT for erasing_user below).
  GRANT SELECT, DELETE ON TABLE public."user" TO core_eraser;
END
$grants$;
"""

# The rule of the one way through. session_user, not current_user: the cascade of a user's delete
# runs the child tables' triggers with the table owner's rights, so current_user is `core` there,
# while session_user stays the login that issued the DELETE. And the user row must already be gone
# (the cascade sees the delete that started it), so deleting one row of history of a user that
# still exists stays refused for everyone.
ERASING_USER = """
CREATE FUNCTION erasing_user(uid uuid) RETURNS boolean LANGUAGE sql STABLE
  SET search_path = public, pg_temp AS $$
  SELECT pg_has_role(session_user, 'core_eraser', 'MEMBER')
     AND NOT EXISTS (SELECT 1 FROM public."user" WHERE id = uid)
$$;
"""

APPEND_ONLY_NEW = """
CREATE OR REPLACE FUNCTION append_only_refuse() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF erasing_user(OLD.user_id) THEN
      RETURN OLD;
    END IF;
  END IF;
  RAISE EXCEPTION '% on % is refused: review history is append-only', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'restrict_violation';
END;
$$;
"""
APPEND_ONLY_OLD = """
CREATE OR REPLACE FUNCTION append_only_refuse() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
  RAISE EXCEPTION '% on % is refused: review history is append-only', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'restrict_violation';
END;
$$;
"""

ATTEMPT_GUARD = """
CREATE OR REPLACE FUNCTION attempt_guard() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
{erase}  IF TG_OP = 'DELETE' OR OLD.status <> 'draft'
     OR NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at
     OR NEW.user_id <> OLD.user_id
     OR NEW.review_session_id IS DISTINCT FROM OLD.review_session_id
     OR NEW.question_id IS DISTINCT FROM OLD.question_id THEN
    RAISE EXCEPTION '% on attempt is refused: only a draft changes, never its keys', TG_OP
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;
"""

REVIEW_SESSION_GUARD = """
CREATE OR REPLACE FUNCTION review_session_guard() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
{erase}  IF TG_OP = 'DELETE' OR OLD.ended_at IS NOT NULL
     OR NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at
     OR NEW.user_id <> OLD.user_id
     OR NEW.learning_day <> OLD.learning_day
     OR NEW.started_at <> OLD.started_at
     OR NEW.subject_id IS DISTINCT FROM OLD.subject_id THEN
    RAISE EXCEPTION '% on review_session is refused: a session changes only until it ends', TG_OP
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;
"""

ERASE_BRANCH = """  IF TG_OP = 'DELETE' THEN
    IF erasing_user(OLD.user_id) THEN
      RETURN OLD;
    END IF;
  END IF;
"""


def upgrade() -> None:
    op.execute(GRANTS)
    op.execute(ERASING_USER)
    op.execute(APPEND_ONLY_NEW)
    op.execute(ATTEMPT_GUARD.format(erase=ERASE_BRANCH))
    op.execute(REVIEW_SESSION_GUARD.format(erase=ERASE_BRANCH))


def downgrade() -> None:
    # Only the functions go back. The roles and their grants stay: they belong to the cluster, are
    # harmless without the eraser rule, and a revoke would lock core_app out of a database that is
    # being stepped down and up again (the tests do, as core_app).
    op.execute(APPEND_ONLY_OLD)
    op.execute(ATTEMPT_GUARD.format(erase=""))
    op.execute(REVIEW_SESSION_GUARD.format(erase=""))
    op.execute("DROP FUNCTION erasing_user(uuid)")
