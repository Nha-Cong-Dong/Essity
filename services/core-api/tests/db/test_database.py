"""T1.2: database foundation. Runs on the real test PostgreSQL (see conftest)."""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Column, Engine, ForeignKey, Integer, MetaData, Table, func, select, text
from sqlalchemy.orm import Session

from core_api.db.base import NAMING_CONVENTION, Base
from core_api.db.models import Subject, User
from core_api.db.session import DbSession
from core_api.repositories.subject import SubjectRepository

# --- Migrations ------------------------------------------------------------------------------


HISTORY_TRIGGERS = {
    "grade_needs_submitted_attempt",
    "grade_unit_with_its_grade",
    "grade_append_only",
    "grade_unit_append_only",
    "review_log_append_only",
    "attempt_guard",
    "review_session_guard",
    "grade_no_truncate",
    "grade_unit_no_truncate",
    "review_log_no_truncate",
    "attempt_no_truncate",
    "review_session_no_truncate",
}
HISTORY_FUNCTIONS = {
    "append_only_refuse",
    "attempt_guard",
    "review_session_guard",
    "grade_needs_submitted_attempt",
    "grade_unit_with_its_grade",
}


def test_migrations_have_one_head(alembic_cfg: Config) -> None:
    # Red when: two branches each add a migration on the same parent (two PRs both numbering
    # theirs 0011, say): `upgrade head` then fails, so the later PR must renumber when rebasing.
    assert len(ScriptDirectory.from_config(alembic_cfg).get_heads()) == 1


def test_migrations_go_down_to_base_and_back_up(engine: Engine, alembic_cfg: Config) -> None:
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    # The append-only guards of 0008 come back with their tables (review final fed95f2).
    with engine.connect() as connection:
        triggers = connection.execute(
            text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
        ).scalars()
        functions = {
            name: config
            for name, config in connection.execute(
                text(
                    "SELECT proname, proconfig FROM pg_proc"
                    " WHERE pronamespace = 'public'::regnamespace"
                )
            )
        }
    assert HISTORY_TRIGGERS <= set(triggers)
    assert HISTORY_FUNCTIONS <= set(functions)
    for name in HISTORY_FUNCTIONS:
        # pg_temp last: a temporary table never stands in for a real one.
        assert functions[name] == ["search_path=public, pg_temp"], name


def test_models_and_migrations_match(engine: Engine, alembic_cfg: Config) -> None:
    # Fails as soon as a model changes without a migration (`alembic check`).
    try:
        command.check(alembic_cfg)
    except CommandError as exc:  # pragma: no cover - the message is the useful part
        pytest.fail(f"models and migrations differ: {exc}")


def test_constraint_names_follow_the_naming_convention() -> None:
    # Alembic can only drop or alter constraints it can name.
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert {"pk", "fk", "uq", "ix", "ck"} <= set(NAMING_CONVENTION)


# --- One session per request -----------------------------------------------------------------


@pytest.fixture
def probe_table(engine: Engine) -> Iterator[None]:
    """A real, committed table: these tests check what get_session commits."""
    with engine.begin() as connection:
        # Unique, but checked only at COMMIT: lets a test make the commit itself fail.
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS probe_request "
                "(value text UNIQUE DEFERRABLE INITIALLY DEFERRED)"
            )
        )
        connection.execute(text("TRUNCATE probe_request"))
    yield
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE probe_request"))


def committed_values(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT value FROM probe_request")).scalars())


@pytest.fixture
def app_with_writes() -> FastAPI:
    app = FastAPI()

    @app.post("/ok")
    def ok(session: DbSession) -> None:
        session.execute(text("INSERT INTO probe_request VALUES ('ok')"))

    @app.post("/fail")
    def fail(session: DbSession) -> None:
        session.execute(text("INSERT INTO probe_request VALUES ('fail')"))
        raise HTTPException(status_code=409)

    @app.post("/crash")
    def crash(session: DbSession) -> None:
        session.execute(text("INSERT INTO probe_request VALUES ('crash')"))
        raise RuntimeError("boom")

    @app.post("/commit-fails")
    def commit_fails(session: DbSession) -> None:
        session.execute(text("INSERT INTO probe_request VALUES ('dup'), ('dup')"))

    _ = (ok, fail, crash, commit_fails)
    return app


def test_request_work_is_committed_on_success(
    engine: Engine, probe_table: None, app_with_writes: FastAPI
) -> None:
    assert TestClient(app_with_writes).post("/ok").status_code == 200
    assert committed_values(engine) == ["ok"]


def test_request_work_is_rolled_back_on_http_error(
    engine: Engine, probe_table: None, app_with_writes: FastAPI
) -> None:
    assert TestClient(app_with_writes).post("/fail").status_code == 409
    assert committed_values(engine) == []


def test_request_work_is_rolled_back_on_crash(
    engine: Engine, probe_table: None, app_with_writes: FastAPI
) -> None:
    client = TestClient(app_with_writes, raise_server_exceptions=False)
    assert client.post("/crash").status_code == 500
    assert committed_values(engine) == []


def test_failed_commit_is_an_error_response_not_a_200(
    engine: Engine, probe_table: None, app_with_writes: FastAPI
) -> None:
    # The commit must happen before the response is sent, or the client hears "saved" for
    # data that was never saved.
    client = TestClient(app_with_writes, raise_server_exceptions=False)
    assert client.post("/commit-fails").status_code == 500
    assert committed_values(engine) == []


# --- Repository scoped to one user -----------------------------------------------------------
# Isolation of each real table is tested with tests/isolation.py; these cover the base class.


def test_repository_refuses_to_exist_without_a_user_id(db_session: Session) -> None:
    for missing in (None, "", str(uuid.uuid4())):
        with pytest.raises(TypeError):
            SubjectRepository(db_session, missing)  # pyright: ignore[reportArgumentType]


def test_repository_sets_the_owner_whatever_the_caller_passes(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    subject = SubjectRepository(db_session, alice.id).add(Subject(name="x", user_id=bob.id))
    assert subject.user_id == alice.id


# --- Each test leaves the database as it found it (run in random order) ----------------------


@pytest.mark.parametrize("attempt", [1, 2])
def test_rows_from_other_tests_are_never_visible(
    db_session: Session, two_users: tuple[User, User], attempt: int
) -> None:
    SubjectRepository(db_session, two_users[0].id).create(f"attempt {attempt}")
    db_session.commit()  # a commit inside a test is still rolled back afterwards
    assert db_session.scalar(select(func.count()).select_from(Subject)) == 1


# --- Deleting a user (ADR-0020 §4: purge_unverified deletes the user row only) ----------------


def foreign_keys_to_user_without_cascade(metadata: MetaData) -> list[str]:
    return sorted(
        f"{table.name}.{fk.parent.name}"
        for table in metadata.tables.values()
        for fk in table.foreign_keys
        if fk.column.table.name == "user" and fk.ondelete != "CASCADE"
    )


def test_every_foreign_key_to_user_cascades_on_delete() -> None:
    """A table that kept a user's row alive would make every purge fail, and retry forever."""
    assert foreign_keys_to_user_without_cascade(Base.metadata) == []


def test_cascade_check_flags_a_foreign_key_without_it() -> None:
    probe = MetaData()
    Table("user", probe, Column("id", Integer, primary_key=True))
    Table("note", probe, Column("user_id", Integer, ForeignKey("user.id")))
    assert foreign_keys_to_user_without_cascade(probe) == ["note.user_id"]
