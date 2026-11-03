"""T2.22, Tester: edges of the eraser path the role tests leave open.

Every test logs in as the real roles (`core_app`, a member of `core_eraser`, the owner `core`),
like tests/db/test_roles.py.
"""

import contextlib
import threading
import uuid
from collections.abc import Generator, Iterator

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from core_api.db.engine import create_db_engine
from core_api.db.models import Subject, User
from core_api.db.role_guard import UnsafeDatabaseRoleError, assert_app_role
from core_api.repositories.user import UserRepository
from erase_world import World, build_world, rows_of, tables_with_user_id
from erasure import erase_user, erase_users
from v2_rows import make_document, make_study_session, make_type

RESTRICT_VIOLATION = "23001"
# outbox keeps a user's events after the user is gone on purpose (`user.deleted.v1` must still be
# sent), so it has a user_id and no foreign key to "user".
NOT_CASCADED = {"outbox"}


def sqlstate(error: BaseException) -> str | None:
    return getattr(getattr(error, "orig", None), "sqlstate", None)


@contextlib.contextmanager
def granted(owner_engine: Engine, privileges: str, table: str) -> Generator[None]:
    with owner_engine.begin() as connection:
        connection.execute(text(f'GRANT {privileges} ON "{table}" TO core_eraser'))
    try:
        yield
    finally:
        with owner_engine.begin() as connection:
            connection.execute(text(f'REVOKE {privileges} ON "{table}" FROM core_eraser'))


def add_tier_three(engine: Engine, user_id: uuid.UUID) -> None:
    """The rows that hang on tier 2 with NO ACTION and the world does not have yet: memory_state,
    practice_state, a question type and a bank document on a question, a study session range on a
    document, a review session tied to a subject."""
    with Session(engine) as session:
        user = session.get(User, user_id)
        assert user is not None
        subject = session.scalars(select(Subject).where(Subject.user_id == user_id)).one()
        document = make_document(session, user, subject, sha=uuid.uuid4().hex * 2)
        question_type = make_type(session, user, subject)
        study = make_study_session(session, user, subject)
        params = {
            "u": user_id,
            "s": subject.id,
            "d": document.id,
            "t": question_type.id,
            "st": study.id,
        }
        session.execute(
            text(
                "INSERT INTO memory_state (id, user_id, unit_id, phase, stability, difficulty,"
                " due, last_review) SELECT gen_random_uuid(), :u, id, 'review', 1, 5, now(),"
                " now() FROM knowledge_unit WHERE user_id = :u"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO practice_state (id, user_id, question_id, phase, stability,"
                " difficulty, due, last_review) SELECT gen_random_uuid(), :u, id, 'review', 1, 5,"
                " now(), now() FROM question WHERE user_id = :u"
            ),
            params,
        )
        session.execute(
            text(
                "UPDATE question SET type_id = :t, bank_document_id = :d, bank_ord = 1"
                " WHERE user_id = :u"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO session_range (id, user_id, session_id, document_id, start_page,"
                " end_page, depth, position) VALUES (gen_random_uuid(), :u, :st, :d, 1, 2,"
                " 'deep', 0)"
            ),
            params,
        )
        session.execute(
            text(
                "INSERT INTO review_session (id, user_id, learning_day, started_at, subject_id)"
                " VALUES (gen_random_uuid(), :u, DATE '2026-10-31', now(), :s)"
            ),
            params,
        )
        session.commit()


@pytest.fixture
def make_world(engine: Engine, eraser_engine: Engine) -> Iterator[list[World]]:
    made: list[World] = []
    yield made
    erase_users(eraser_engine, [world.user_id for world in made])


def new_world(engine: Engine, made: list[World]) -> World:
    world = build_world(engine)
    made.append(world)
    return world


def test_t222t_every_table_with_a_user_id_cascades_from_user(owner_engine: Engine) -> None:
    # Red when: a table gets a user_id without `REFERENCES "user" ON DELETE CASCADE` (a later
    # migration): the eraser's one DELETE FROM "user" would then fail or leave that user's rows.
    with owner_engine.connect() as connection:
        cascaded = set(
            connection.scalars(
                text(
                    "SELECT k.conrelid::regclass::text FROM pg_constraint k"
                    " JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = ANY (k.conkey)"
                    " WHERE k.contype = 'f' AND k.confrelid = 'public.\"user\"'::regclass"
                    " AND a.attname = 'user_id' AND k.confdeltype = 'c'"
                )
            )
        )
    missing = set(tables_with_user_id(owner_engine)) - cascaded - NOT_CASCADED
    assert missing == set()


def test_t222t_erasing_a_user_with_no_data_and_an_unknown_id(
    engine: Engine, eraser_engine: Engine
) -> None:
    # Red when: the eraser path needs history to exist (a bare account cannot be erased) or an id
    # that is already gone raises instead of deleting nothing (a retried erase must be harmless).
    with Session(engine) as session:
        user = UserRepository(session).create(f"bare-{uuid.uuid4().hex[:12]}@example.com")
        session.commit()
        user_id = user.id
    erase_user(eraser_engine, user_id)
    assert set(rows_of(engine, user_id).values()) == {0}
    with eraser_engine.begin() as connection:
        gone = connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": user_id})
        assert gone.rowcount == 0


def test_t222t_erase_reaches_every_no_action_edge_of_tier_three(
    engine: Engine, eraser_engine: Engine, make_world: list[World]
) -> None:
    # Tester T2.3: tier 3 hangs on tier 2 with NO ACTION (memory_state -> unit, practice_state ->
    # question, question -> type and bank document, session_range -> document, review_session ->
    # subject, grade_unit -> grade, practice_log -> grade). Red when: one of those rows is not
    # cleared by the same statement, so the NO ACTION check at its end refuses the whole erase.
    a, b = new_world(engine, make_world), new_world(engine, make_world)
    add_tier_three(engine, a.user_id)
    add_tier_three(engine, b.user_id)
    a_before, b_before = rows_of(engine, a.user_id), rows_of(engine, b.user_id)
    for table in ("memory_state", "practice_state", "session_range", "question_type", "document"):
        assert a_before[table] >= 1, table
    erase_user(eraser_engine, a.user_id)
    assert set(rows_of(engine, a.user_id).values()) == {0}
    assert rows_of(engine, b.user_id) == b_before


def test_t222t_two_users_in_one_statement_keep_the_third(
    engine: Engine, eraser_engine: Engine, make_world: list[World]
) -> None:
    # Red when: the rule holds for one user per statement only (e.g. the user row is looked up
    # once, or the first user's rows are refused while the second is still being deleted).
    a, b, c = (new_world(engine, make_world) for _ in range(3))
    c_before = rows_of(engine, c.user_id)
    with eraser_engine.begin() as connection:
        connection.execute(
            text('DELETE FROM "user" WHERE id IN (:a, :b)'), {"a": a.user_id, "b": b.user_id}
        )
    assert set(rows_of(engine, a.user_id).values()) == {0}
    assert set(rows_of(engine, b.user_id).values()) == {0}
    assert rows_of(engine, c.user_id) == c_before


def test_t222t_two_erasers_at_the_same_time(
    engine: Engine, eraser_engine: Engine, make_world: list[World]
) -> None:
    # Two admin sessions erase two users at once, both holding their transaction open until the
    # other has deleted too. Red when: the erases lock each other (a shared row, a deadlock) or one
    # reaches into the other's rows.
    a, b, c = (new_world(engine, make_world) for _ in range(3))
    c_before = rows_of(engine, c.user_id)
    both_deleted = threading.Barrier(2, timeout=10)
    errors: list[BaseException] = []

    def erase(user_id: uuid.UUID) -> None:
        try:
            with eraser_engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": user_id})
                both_deleted.wait()
        except BaseException as error:  # noqa: BLE001 - reported below
            errors.append(error)
            both_deleted.abort()

    threads = [
        threading.Thread(target=erase, args=(user_id,)) for user_id in (a.user_id, b.user_id)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    assert set(rows_of(engine, a.user_id).values()) == {0}
    assert set(rows_of(engine, b.user_id).values()) == {0}
    assert rows_of(engine, c.user_id) == c_before


@pytest.mark.parametrize(
    ("table", "where"),
    [
        ("grade_unit", "user_id = :u"),
        ("review_session_item", "user_id = :u"),
        ("attempt", "user_id = :u AND status = 'draft'"),
        ("review_session", "id = :s"),
    ],
)
def test_t222t_eraser_cannot_delete_guarded_rows_while_the_user_exists(
    engine: Engine,
    eraser_engine: Engine,
    owner_engine: Engine,
    make_world: list[World],
    table: str,
    where: str,
) -> None:
    # The tables the role tests do not try directly: the two other append-only tables, a draft
    # attempt (attempt_guard) and a session that has not ended (review_session_guard). The DELETE
    # privilege is lent so that only the trigger can refuse. Red when: the eraser branch of a guard
    # lets a member of core_eraser through without the user being gone.
    world = new_world(engine, make_world)
    params = {"u": world.user_id, "s": world.session_id}
    before = rows_of(engine, world.user_id)
    with granted(owner_engine, "SELECT, DELETE", table):
        with pytest.raises(DBAPIError) as refused, eraser_engine.begin() as connection:
            deleted = connection.execute(text(f'DELETE FROM "{table}" WHERE {where}'), params)  # noqa: S608
            assert deleted.rowcount >= 1  # only reached when the guard let it through
        assert sqlstate(refused.value) == RESTRICT_VIOLATION
        assert "is refused" in str(refused.value)
    assert rows_of(engine, world.user_id) == before


def test_t222t_tables_made_by_later_migrations_reach_core_app(owner_engine: Engine) -> None:
    # Red when: ALTER DEFAULT PRIVILEGES is missing or narrower: every M7-M9 table would then fail
    # for the app at run time, or core_app/core_eraser would get more than planned on it.
    privileges = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER", "REFERENCES")
    with owner_engine.connect() as connection, connection.begin() as transaction:
        connection.execute(text("CREATE TABLE public.t222t_later (id bigserial PRIMARY KEY)"))
        app = {
            p
            for p in privileges
            if connection.scalar(
                text("SELECT has_table_privilege('core_app', 'public.t222t_later', :p)"),
                {"p": p},
            )
        }
        eraser = {
            p
            for p in privileges
            if connection.scalar(
                text("SELECT has_table_privilege('core_eraser', 'public.t222t_later', :p)"),
                {"p": p},
            )
        }
        sequence = connection.scalar(
            text(
                "SELECT has_sequence_privilege('core_app', 'public.t222t_later_id_seq',"
                " 'USAGE') AND has_sequence_privilege('core_app', 'public.t222t_later_id_seq',"
                " 'SELECT')"
            )
        )
        transaction.rollback()
    assert app == {"SELECT", "INSERT", "UPDATE", "DELETE"}
    assert eraser == set()
    assert sequence is True


def test_t222t_core_app_can_use_every_sequence(engine: Engine) -> None:
    # Red when: the sequence GRANT is missing: an INSERT into a serial/identity table (the job
    # queue, the outbox) would fail for the app with "permission denied for sequence".
    with engine.connect() as connection:
        refused = list(
            connection.scalars(
                text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " WHERE n.nspname = 'public' AND c.relkind = 'S'"
                    " AND NOT (has_sequence_privilege(c.oid, 'USAGE')"
                    " AND has_sequence_privilege(c.oid, 'SELECT'))"
                )
            )
        )
    assert refused == []


@contextlib.contextmanager
def login_with(owner_engine: Engine, attribute: str) -> Generator[Engine]:
    """A throwaway login with one role attribute and no ownership. The owner needs CREATEROLE and
    the attribute itself (a superuser in CI); elsewhere the test skips."""
    column = {"CREATEDB": "rolcreatedb", "CREATEROLE": "rolcreaterole", "BYPASSRLS": "rolbypassrls"}
    with owner_engine.connect() as connection:
        can = connection.scalar(
            text(
                f"SELECT rolsuper OR (rolcreaterole AND {column[attribute]})"
                " FROM pg_roles WHERE rolname = current_user"
            )
        )
    if not can:
        pytest.skip("the owner cannot create such a login here (it can in CI)")
    name, password = f"t222t_{uuid.uuid4().hex[:8]}", "probe-password"
    database = owner_engine.url.database
    with owner_engine.begin() as connection:
        connection.execute(text(f"CREATE ROLE \"{name}\" LOGIN {attribute} PASSWORD '{password}'"))
        connection.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO "{name}"'))
    probe = create_db_engine(
        owner_engine.url.set(username=name, password=password).render_as_string(hide_password=False)
    )
    try:
        yield probe
    finally:
        probe.dispose()
        with owner_engine.begin() as connection:
            # Not DROP OWNED: it needs the probe's privileges, which a CREATEROLE owner lacks.
            connection.execute(text(f'REVOKE CONNECT ON DATABASE "{database}" FROM "{name}"'))
            connection.execute(text(f'DROP ROLE "{name}"'))


@pytest.mark.parametrize("attribute", ["CREATEDB", "CREATEROLE", "BYPASSRLS"])
def test_t222t_the_guard_refuses_a_privileged_login_that_owns_nothing(
    owner_engine: Engine, attribute: str
) -> None:
    # The role guard tests refuse the owner (it owns the tables) and the eraser; neither shows the
    # attribute half on its own. Red when: the guard drops rolcreatedb/rolcreaterole/rolbypassrls
    # (BYPASSRLS would void the row level security of T6.1).
    with login_with(owner_engine, attribute) as probe:
        with pytest.raises(UnsafeDatabaseRoleError, match="superuser, CREATEROLE"):
            assert_app_role(probe)
