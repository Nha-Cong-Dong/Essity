"""T2.22: core-api refuses to start as the owner, a superuser or the eraser (outside local/test).

The guard asks the database what the login is, so each case logs in as the real thing.
"""

import contextlib
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text

import core_api.jobs.worker as worker
import core_api.main as main
from core_api.config import Settings
from core_api.db.engine import create_db_engine
from core_api.db.role_guard import UnsafeDatabaseRoleError, assert_app_role, check_app_role


def settings_for(url: str, environment: str) -> Settings:
    # No validation: a production Settings needs a dozen unrelated values the guard never reads.
    return Settings.model_construct(environment=environment, database_url=SecretStr(url))


def test_t222_the_app_login_passes(engine: Engine) -> None:
    assert_app_role(engine)


def test_t222_the_owner_is_refused(owner_engine: Engine) -> None:
    # Red when: the guard does not notice a login that owns the tables (or is a superuser, in CI).
    with pytest.raises(UnsafeDatabaseRoleError, match="core_app"):
        assert_app_role(owner_engine)


def test_t222_a_member_of_core_eraser_is_refused(eraser_engine: Engine) -> None:
    # Red when: an app login that can erase history starts without a word.
    with pytest.raises(UnsafeDatabaseRoleError, match="core_eraser"):
        assert_app_role(eraser_engine)


@contextlib.contextmanager
def probe_login(owner_engine: Engine, *grants: str) -> Generator[Engine]:
    """A throwaway login that is a member of the given roles. Needs CREATEROLE: CI's owner is a
    superuser; locally the owner is not, and the tests that need it skip."""
    with owner_engine.connect() as connection:
        if not connection.scalar(
            text("SELECT rolcreaterole OR rolsuper FROM pg_roles WHERE rolname = current_user")
        ):
            pytest.skip("the owner cannot create roles here (it can in CI)")
    name, password = f"guard_probe_{uuid.uuid4().hex[:8]}", "probe-password"
    with owner_engine.begin() as connection:
        connection.execute(text(f"CREATE ROLE \"{name}\" LOGIN PASSWORD '{password}'"))
        for role in grants:
            connection.execute(text(f'GRANT "{role}" TO "{name}"'))
        connection.execute(
            text(f'GRANT CONNECT ON DATABASE "{_database(owner_engine)}" TO "{name}"')
        )
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{name}"'))
    url = owner_engine.url.set(username=name, password=password)
    probe = create_db_engine(url.render_as_string(hide_password=False))
    try:
        yield probe
    finally:
        probe.dispose()
        with owner_engine.begin() as connection:
            connection.execute(text(f'DROP OWNED BY "{name}"'))
            connection.execute(text(f'DROP ROLE "{name}"'))


def _database(engine: Engine) -> str:
    return engine.url.database or ""


def test_t222_a_member_of_the_owner_role_is_refused(owner_engine: Engine) -> None:
    # Red when: the guard compares the table owner to the login's name only (`GRANT core TO login`
    # gives the login the owner's rights without being the owner).
    with owner_engine.connect() as connection:
        owner = connection.scalar(
            text("SELECT tableowner FROM pg_tables WHERE tablename = 'grade'")
        )
    assert isinstance(owner, str)
    with probe_login(owner_engine, owner) as probe, pytest.raises(UnsafeDatabaseRoleError):
        assert_app_role(probe)


def test_t222_a_member_of_core_eraser_with_another_name_is_refused(owner_engine: Engine) -> None:
    with probe_login(owner_engine, "core_eraser") as probe, pytest.raises(UnsafeDatabaseRoleError):
        assert_app_role(probe)


def test_t222_local_and_test_skip_the_check(owner_engine: Engine) -> None:
    url = owner_engine.url.render_as_string(hide_password=False)
    for environment in ("local", "test"):
        check_app_role(settings_for(url, environment))  # the owner, and no error


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_t222_other_environments_run_the_check(owner_engine: Engine, environment: str) -> None:
    url = owner_engine.url.render_as_string(hide_password=False)
    with pytest.raises(UnsafeDatabaseRoleError):
        check_app_role(settings_for(url, environment))


def test_t222_the_api_startup_runs_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    # Red when: the lifespan never calls it, so a misconfigured deploy starts as the owner.
    class Refused(Exception):
        pass

    def refuse(settings: Settings) -> None:
        raise Refused

    monkeypatch.setattr(main, "check_app_role", refuse)
    with pytest.raises(Refused), TestClient(main.app):
        pass


def test_t222_the_worker_startup_runs_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    class Refused(Exception):
        pass

    def refuse(settings: Settings) -> None:
        raise Refused

    monkeypatch.setattr(worker, "check_app_role", refuse)
    with pytest.raises(Refused):
        worker.main()
