"""T1.2: database foundation. Runs on the real test PostgreSQL (see conftest)."""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from core_api.db.base import NAMING_CONVENTION, Base
from core_api.db.models import Subject, User
from core_api.db.session import DbSession
from core_api.repositories.subject import SubjectRepository

# --- Migrations ------------------------------------------------------------------------------


def test_migrations_go_down_to_base_and_back_up(engine: Engine, alembic_cfg: Config) -> None:
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")


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
