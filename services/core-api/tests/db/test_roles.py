"""T2.22: the three database roles. Every test logs in as the real role (`core_app`, a member of
`core_eraser`): no SET ROLE from a superuser, which would hide what each login can really do.

Where the grant of a role would already refuse a statement, the test lends the privilege to
core_eraser first, so that what refuses it is the trigger (the SQLSTATE and message), not a
permission error that proves nothing about the trigger.
"""

import contextlib
import uuid
from collections.abc import Generator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session

from core_api.jobs.purge_unverified import UNVERIFIED_LIFETIME, purge_unverified
from core_api.repositories.user import UserRepository
from erase_world import World, build_world, rows_of, tables_with_user_id
from erasure import erase_user

RESTRICT_VIOLATION = "23001"
INSUFFICIENT_PRIVILEGE = "42501"
LOCK_NOT_AVAILABLE = "55P03"
# Every table whose rows the append-only function protects (migrations 0008, 0010, 0025, 0032).
APPEND_ONLY = [
    "grade",
    "grade_unit",
    "practice_log",
    "practice_removal_log",
    "review_log",
    "review_session_item",
]


def sqlstate(error: BaseException) -> str | None:
    return getattr(getattr(error, "orig", None), "sqlstate", None)


@pytest.fixture
def world(engine: Engine, eraser_engine: Engine) -> Iterator[World]:
    made = build_world(engine)
    yield made
    erase_user(eraser_engine, made.user_id)


@pytest.fixture
def other_world(engine: Engine, eraser_engine: Engine) -> Iterator[World]:
    made = build_world(engine)
    yield made
    erase_user(eraser_engine, made.user_id)


@contextlib.contextmanager
def granted(owner_engine: Engine, privileges: str, table: str) -> Generator[None]:
    """Lend core_eraser extra privileges for one test, so a refusal can only come from a trigger."""
    with owner_engine.begin() as connection:
        connection.execute(text(f'GRANT {privileges} ON "{table}" TO core_eraser'))
    try:
        yield
    finally:
        with owner_engine.begin() as connection:
            connection.execute(text(f'REVOKE {privileges} ON "{table}" FROM core_eraser'))


# --- the roles themselves --------------------------------------------------------------------


def test_t222_roles_exist_with_the_right_attributes(owner_engine: Engine) -> None:
    # Red when: roles.sql was not run, or core_app can create roles/databases or bypass RLS.
    with owner_engine.connect() as connection:
        rows = {
            row.rolname: row
            for row in connection.execute(
                text(
                    "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls,"
                    " rolcanlogin FROM pg_roles WHERE rolname IN ('core_app', 'core_eraser')"
                )
            )
        }
    assert set(rows) == {"core_app", "core_eraser"}
    app, eraser = rows["core_app"], rows["core_eraser"]
    assert app.rolcanlogin and not eraser.rolcanlogin
    for role in (app, eraser):
        assert not (role.rolsuper or role.rolcreatedb or role.rolcreaterole or role.rolbypassrls)


def test_t222_engines_log_in_as_the_real_roles(
    engine: Engine, eraser_engine: Engine, owner_engine: Engine
) -> None:
    # Red when: the test suite still runs as the owner, so nothing here proves what the app can do.
    def who(target: Engine) -> tuple[str, str]:
        with target.connect() as connection:
            row = connection.execute(text("SELECT current_user, session_user")).one()
        return row[0], row[1]

    assert who(engine) == ("core_app", "core_app")
    assert who(owner_engine)[0] == "core"
    login = who(eraser_engine)[0]
    with owner_engine.connect() as connection:
        assert connection.scalar(
            text("SELECT pg_has_role(:r, 'core_eraser', 'MEMBER')"), {"r": login}
        )


def test_t222_core_app_is_not_a_member_of_the_owner_or_the_eraser(engine: Engine) -> None:
    # Red when: a GRANT makes the app role the owner or the eraser in disguise.
    with engine.connect() as connection:
        owner = connection.scalar(
            text("SELECT tableowner FROM pg_tables WHERE tablename = 'grade'")
        )
        assert owner != "core_app"
        assert not connection.scalar(text("SELECT pg_has_role('core_eraser', 'MEMBER')"))
        assert not connection.scalar(text("SELECT pg_has_role(:o, 'MEMBER')"), {"o": owner})


def test_t222_privileges_are_exactly_the_planned_ones(
    engine: Engine, eraser_engine: Engine
) -> None:
    # Red when: core_app gets TRUNCATE/TRIGGER/REFERENCES (TRIGGER lets it create triggers without
    # owning the table), loses a CRUD privilege, reads alembic_version, or core_eraser gets more
    # than SELECT and DELETE on "user".
    def privileges(target: Engine, table: str) -> set[str]:
        with target.connect() as connection:
            return {
                p
                for p in (
                    "SELECT",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "TRUNCATE",
                    "TRIGGER",
                    "REFERENCES",
                )
                if connection.scalar(
                    text("SELECT has_table_privilege(current_user, :t, :p)"),
                    {"t": f'public."{table}"', "p": p},
                )
            }

    with engine.connect() as connection:
        tables = list(
            connection.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        )
    assert "grade" in tables and "alembic_version" in tables
    for table in tables:
        have = privileges(engine, table)
        want: set[str] = (
            set() if table == "alembic_version" else {"SELECT", "INSERT", "UPDATE", "DELETE"}
        )
        assert have == want, (table, have)
        assert privileges(eraser_engine, table) == (
            {"SELECT", "DELETE"} if table == "user" else set()
        ), table


def test_t222_every_append_only_table_is_known_and_has_a_user_id(
    engine: Engine, owner_engine: Engine
) -> None:
    # Red when: a new append-only table is added without a user_id (the eraser rule needs it) or
    # without being listed here, so nobody decided how core_eraser clears it.
    with owner_engine.connect() as connection:
        guarded = set(
            connection.scalars(
                text(
                    "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
                    " JOIN pg_proc p ON p.oid = t.tgfoid WHERE p.proname = 'append_only_refuse'"
                    " AND NOT t.tgisinternal"
                )
            )
        )
    # attempt and review_session carry only the no-truncate trigger of the same function.
    assert guarded == {*APPEND_ONLY, "attempt", "review_session"}
    assert set(APPEND_ONLY) <= set(tables_with_user_id(engine))


# --- core_app --------------------------------------------------------------------------------


@pytest.mark.parametrize("table", APPEND_ONLY)
def test_t222_core_app_cannot_delete_update_or_truncate_history(
    engine: Engine, world: World, table: str
) -> None:
    # Red when: a trigger is gone or core_app is allowed through. DELETE and UPDATE are refused by
    # the trigger (core_app holds the privilege), TRUNCATE by a missing privilege.
    for statement in (f'DELETE FROM "{table}"', f'UPDATE "{table}" SET user_id = user_id'):
        with pytest.raises(DBAPIError) as refused, engine.begin() as connection:
            connection.execute(text(statement))
        assert sqlstate(refused.value) == RESTRICT_VIOLATION, statement
        assert "is refused" in str(refused.value)
    with pytest.raises(ProgrammingError) as no_truncate, engine.begin() as connection:
        connection.execute(text(f'TRUNCATE "{table}"'))
    assert sqlstate(no_truncate.value) == INSUFFICIENT_PRIVILEGE


def test_t222_core_app_cannot_delete_a_user_with_history(engine: Engine, world: World) -> None:
    # Red when: the cascade runs the bypass for the app role. In CI the owner is a superuser, so
    # a bypass that looked at current_user (the table owner inside a cascade) is caught here.
    before = rows_of(engine, world.user_id)
    with pytest.raises(DBAPIError) as refused, engine.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": world.user_id})
    assert sqlstate(refused.value) == RESTRICT_VIOLATION
    assert rows_of(engine, world.user_id) == before  # the whole statement rolled back
    assert before["user"] == 1 and before["grade"] == 1


def test_t222_core_app_cannot_disable_a_trigger(engine: Engine) -> None:
    with pytest.raises(ProgrammingError, match="must be owner") as refused, engine.begin() as c:
        c.execute(text("ALTER TABLE grade DISABLE TRIGGER ALL"))
    assert sqlstate(refused.value) == INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE public.t222_probe (x int)",
        "CREATE OR REPLACE FUNCTION public.append_only_refuse() RETURNS trigger"
        " LANGUAGE plpgsql AS $$ BEGIN RETURN OLD; END $$",
    ],
)
def test_t222_core_app_cannot_create_a_table_or_replace_a_trigger_function(
    engine: Engine, statement: str
) -> None:
    with pytest.raises(ProgrammingError) as refused, engine.begin() as connection:
        connection.execute(text(statement))
    assert sqlstate(refused.value) == INSUFFICIENT_PRIVILEGE


def test_t222_purge_unverified_still_runs_as_core_app(engine: Engine) -> None:
    # Red when: a GRANT is missing for what the purge job touches.
    now = datetime(2026, 11, 1, tzinfo=UTC)
    with Session(engine) as session:
        stale = UserRepository(session).create(f"purge-{uuid.uuid4().hex[:12]}@example.com")
        stale.created_at = now - UNVERIFIED_LIFETIME - timedelta(days=1)
        stale_id = stale.id
        session.commit()
        assert purge_unverified(session, now) >= 1
        session.commit()
        gone = session.scalar(text('SELECT count(*) FROM "user" WHERE id = :u'), {"u": stale_id})
        assert gone == 0


# --- core_eraser -----------------------------------------------------------------------------


def test_t222_eraser_deletes_every_table_of_user_a_and_keeps_user_b(
    engine: Engine, eraser_engine: Engine, world: World, other_world: World
) -> None:
    # Red when: one guard function lacks the bypass, or the cascade does not see the user gone.
    a_before, b_before = rows_of(engine, world.user_id), rows_of(engine, other_world.user_id)
    for table in (*APPEND_ONLY, "attempt", "review_session", "command_log"):
        assert a_before[table] >= 1, table
    erase_user(eraser_engine, world.user_id)
    assert set(rows_of(engine, world.user_id).values()) == {0}
    assert rows_of(engine, other_world.user_id) == b_before


@pytest.mark.parametrize("table", ["grade", "review_log", "practice_log", "practice_removal_log"])
def test_t222_eraser_cannot_touch_history_while_the_user_exists(
    engine: Engine, eraser_engine: Engine, owner_engine: Engine, world: World, table: str
) -> None:
    # Red when: the bypass does not look at the user row. The privileges are lent to core_eraser
    # here so that the refusal is the trigger's (23001, "is refused"), not a missing GRANT.
    before = rows_of(engine, world.user_id)
    with granted(owner_engine, "SELECT, DELETE, UPDATE", table):
        for statement in (
            f'DELETE FROM "{table}" WHERE user_id = :u',
            f'UPDATE "{table}" SET user_id = user_id WHERE user_id = :u',
        ):
            with pytest.raises(DBAPIError) as refused, eraser_engine.begin() as connection:
                connection.execute(text(statement), {"u": world.user_id})
            assert sqlstate(refused.value) == RESTRICT_VIOLATION, statement
            assert "is refused" in str(refused.value)
    assert rows_of(engine, world.user_id) == before


def test_t222_eraser_cannot_truncate_history(
    eraser_engine: Engine, owner_engine: Engine, world: World
) -> None:
    with granted(owner_engine, "SELECT, TRUNCATE", "practice_log"):
        with pytest.raises(DBAPIError) as refused, eraser_engine.begin() as connection:
            connection.execute(text("TRUNCATE practice_log"))
        assert sqlstate(refused.value) == RESTRICT_VIOLATION


def test_t222_the_erasing_rule_is_the_session_user_and_the_user_row(
    engine: Engine, eraser_engine: Engine, world: World
) -> None:
    # Red when: the rule drops either half. erasing_user(A) is false while A exists, true for a
    # user that is gone (checked inside the same transaction as the delete), false for core_app.
    params = {"u": world.user_id}
    with eraser_engine.connect() as connection:
        assert connection.scalar(text("SELECT erasing_user(:u)"), params) is False
        assert connection.scalar(text("SELECT erasing_user(gen_random_uuid())")) is True
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT erasing_user(gen_random_uuid())")) is False


@pytest.fixture
def definer_delete(owner_engine: Engine) -> Iterator[None]:
    """A SECURITY DEFINER function of the owner that deletes a user: inside it current_user is the
    owner, session_user still the caller (what a future erase function would look like)."""
    with owner_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION public.t222_definer_delete(uid uuid) RETURNS void"
                " LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp"
                ' AS $$ DELETE FROM public."user" WHERE id = uid $$'
            )
        )
    yield
    with owner_engine.begin() as connection:
        connection.execute(text("DROP FUNCTION public.t222_definer_delete(uuid)"))


def test_t222_erasing_follows_session_user_not_current_user(
    engine: Engine, eraser_engine: Engine, world: World, definer_delete: None
) -> None:
    # Inside the definer function current_user is the owner, never core_app or the eraser; the rule
    # reads session_user, the caller. Red when: it is written with current_user, which refuses the
    # eraser here (locally: the owner is not a member of core_eraser) or lets core_app through (the
    # owner is a superuser in CI, where test_t222_core_app_cannot_delete_a_user_with_history and
    # the second half of this test catch it).
    call = text("SELECT t222_definer_delete(:u)")
    params = {"u": world.user_id}
    with pytest.raises(DBAPIError) as refused, engine.begin() as connection:
        connection.execute(call, params)
    assert sqlstate(refused.value) == RESTRICT_VIOLATION
    assert rows_of(engine, world.user_id)["user"] == 1
    with eraser_engine.begin() as connection:
        connection.execute(call, params)
    assert set(rows_of(engine, world.user_id).values()) == {0}


def test_t222_erase_waits_for_an_insert_in_flight_and_then_clears_it(
    engine: Engine, eraser_engine: Engine, world: World
) -> None:
    # A row being written for A holds A's user row (FOR KEY SHARE): the erase must wait for it,
    # never leave the new row behind. Red when: the delete does not conflict with the insert.
    with engine.connect() as writer:
        writer.execute(
            text(
                "INSERT INTO practice_removal_log (user_id, question_id, action)"
                " SELECT user_id, question_id, 'readded' FROM practice_removal_log"
                " WHERE user_id = :u LIMIT 1"
            ),
            {"u": world.user_id},
        )
        with pytest.raises(DBAPIError) as waited, eraser_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '200ms'"))
            connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": world.user_id})
        assert sqlstate(waited.value) == LOCK_NOT_AVAILABLE
        writer.commit()
    erase_user(eraser_engine, world.user_id)
    assert set(rows_of(engine, world.user_id).values()) == {0}
