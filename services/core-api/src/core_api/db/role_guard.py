"""Refuse to run as a login that can undo the database's own protections (T2.22, ADR-0024).

core-api and core-worker must connect as `core_app`: no ownership, no superuser, not the eraser.
A deployment pointed by mistake at the owner (`core`, who may `ALTER TABLE ... DISABLE TRIGGER`) or
at a superuser would work, and quietly lose the append-only history's guarantees. So the check asks
the database what the login is (membership included: `GRANT core TO app_login` is an owner too),
not what the URL says: a superuser can be called anything.
"""

import sqlalchemy
from sqlalchemy import text

from core_api.config import DEV_ENVIRONMENTS, Settings
from core_api.db.engine import engine_for

ERASER_ROLE = "core_eraser"

_PROBE = text(
    """
    SELECT current_user AS name,
           (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls) AS privileged,
           EXISTS (SELECT 1 FROM pg_tables t WHERE t.schemaname = 'public'
                   AND pg_has_role(current_user, t.tableowner, 'MEMBER')) AS owns_tables,
           (EXISTS (SELECT 1 FROM pg_roles e WHERE e.rolname = :eraser)
            AND pg_has_role(session_user, :eraser, 'MEMBER')) AS erases
    FROM pg_roles r WHERE r.rolname = current_user
    """
)


class UnsafeDatabaseRoleError(RuntimeError):
    """The login is the schema owner, a superuser, or a member of core_eraser."""


def assert_app_role(engine: sqlalchemy.Engine) -> None:
    with engine.connect() as connection:
        row = connection.execute(_PROBE, {"eraser": ERASER_ROLE}).one()
    problems = [
        reason
        for reason, found in (
            ("has superuser, CREATEROLE, CREATEDB or BYPASSRLS", row.privileged),
            ("owns (or is a member of the owner of) tables", row.owns_tables),
            (f"is a member of {ERASER_ROLE}", row.erases),
        )
        if found
    ]
    if problems:
        raise UnsafeDatabaseRoleError(
            f"database login {row.name!r} {' and '.join(problems)}: "
            "core-api must connect as core_app (ADR-0024)"
        )


def check_app_role(settings: Settings) -> None:
    """The startup check of core-api and core-worker; local and test run on whatever they have."""
    if settings.environment in DEV_ENVIRONMENTS:
        return
    engine = engine_for(settings)
    try:
        assert_app_role(engine)
    finally:
        engine.dispose()
