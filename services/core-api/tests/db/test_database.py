"""T1.2: database foundation. Runs on the real test PostgreSQL (see conftest)."""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, MetaData, String, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from core_api.db.base import NAMING_CONVENTION, Base, UserOwned
from core_api.db.session import DbSession
from core_api.repositories.base import UserScopedRepository

# --- Test-only models, on their own metadata so `alembic check` never sees them -------------


class ProbeBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Note(UserOwned, ProbeBase):
    __tablename__ = "probe_note"

    body: Mapped[str] = mapped_column(String(200))


class NoteRepository(UserScopedRepository[Note]):
    model = Note


@pytest.fixture
def notes(db_session: Session) -> Session:
    """`probe_note` exists for this test only: DDL is transactional in PostgreSQL."""
    ProbeBase.metadata.create_all(db_session.connection())
    return db_session


ALICE = uuid.uuid4()
BOB = uuid.uuid4()


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


def test_repository_refuses_to_exist_without_a_user_id(notes: Session) -> None:
    for missing in (None, "", str(ALICE)):
        with pytest.raises(TypeError):
            NoteRepository(notes, missing)  # pyright: ignore[reportArgumentType]


def test_repository_only_sees_its_own_users_rows(notes: Session) -> None:
    alice, bob = NoteRepository(notes, ALICE), NoteRepository(notes, BOB)
    mine = alice.add(Note(body="ghi chú của Alice"))
    bob.add(Note(body="ghi chú của Bob"))
    notes.flush()

    assert [n.body for n in alice.list()] == ["ghi chú của Alice"]
    assert alice.get(mine.id) is mine
    assert bob.get(mine.id) is None


def test_repository_sets_the_owner_whatever_the_caller_passes(notes: Session) -> None:
    note = NoteRepository(notes, ALICE).add(Note(body="x", user_id=BOB))
    assert note.user_id == ALICE


def test_repository_delete_cannot_touch_another_users_row(notes: Session) -> None:
    mine = NoteRepository(notes, ALICE).add(Note(body="x"))
    notes.flush()
    assert NoteRepository(notes, BOB).delete(mine.id) is False
    assert NoteRepository(notes, ALICE).delete(mine.id) is True
    notes.flush()
    assert notes.scalar(select(func.count()).select_from(Note)) == 0


# --- Each test leaves the database as it found it (run in random order) ----------------------


@pytest.mark.parametrize("attempt", [1, 2])
def test_rows_from_other_tests_are_never_visible(notes: Session, attempt: int) -> None:
    NoteRepository(notes, ALICE).add(Note(body=f"attempt {attempt}"))
    notes.commit()  # a commit inside a test is still rolled back afterwards
    assert notes.scalar(select(func.count()).select_from(Note)) == 1
