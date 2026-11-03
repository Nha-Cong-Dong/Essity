"""T6.3: `python -m core_api.cli erase-user` and the secrets it must not print."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from core_api import cli
from core_api.clients.storage import S3Storage
from erase_world import World, build_world, rows_of
from erasure import erase_user as erase_rows
from fake_storage import FakeStorage


@pytest.fixture
def world(engine: Engine, eraser_engine: Engine) -> Iterator[World]:
    made = build_world(engine)
    yield made
    erase_rows(eraser_engine, made.user_id)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM outbox WHERE user_id = :u"), {"u": made.user_id})
        connection.execute(
            text("DELETE FROM procrastinate_jobs WHERE args->'payload'->>'user_id' = :u"),
            {"u": str(made.user_id)},
        )


@pytest.fixture
def eraser_url(eraser_engine: Engine) -> str:
    return eraser_engine.url.render_as_string(hide_password=False)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> FakeStorage:
    fake = FakeStorage()

    def from_settings(settings: object) -> FakeStorage:
        return fake

    monkeypatch.setattr(S3Storage, "from_settings", from_settings)
    return fake


def email_of(engine: Engine, user: uuid.UUID) -> str:
    with engine.connect() as connection:
        return str(connection.scalar(text('SELECT email FROM "user" WHERE id = :u'), {"u": user}))


def test_t63_cli_without_the_eraser_url_refuses_and_changes_nothing(
    engine: Engine,
    world: World,
    storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Red when: the command falls back to the app's own URL (which can only half erase).
    monkeypatch.delenv("CORE_ERASER_DATABASE_URL", raising=False)
    email = email_of(engine, world.user_id)
    status = cli.main(["erase-user", "--user-id", str(world.user_id), "--confirm-email", email])
    assert status == 1
    assert "CORE_ERASER_DATABASE_URL" in capsys.readouterr().err
    assert rows_of(engine, world.user_id)["user"] == 1


def test_t63_cli_needs_the_email_while_the_user_exists(
    eraser_url: str,
    engine: Engine,
    world: World,
    storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Red when: a mistyped uuid erases a person.
    monkeypatch.setenv("CORE_ERASER_DATABASE_URL", eraser_url)
    assert cli.main(["erase-user", "--user-id", str(world.user_id)]) == 1
    assert "refused" in capsys.readouterr().err
    assert rows_of(engine, world.user_id)["user"] == 1


def test_t63_cli_erases_with_the_eraser_login_and_runs_again(
    eraser_url: str,
    engine: Engine,
    world: World,
    storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Red when: the command does not finish, or running it a second time (no email: the user is
    # gone) fails.
    monkeypatch.setenv("CORE_ERASER_DATABASE_URL", eraser_url)
    storage.put(f"users/{world.user_id}/raw/a.pdf", b"x", None)
    email = email_of(engine, world.user_id)
    args = ["erase-user", "--user-id", str(world.user_id)]

    assert cli.main([*args, "--confirm-email", email]) == 0
    assert rows_of(engine, world.user_id)["user"] == 0
    assert not storage.objects
    assert cli.main(args) == 0
    assert email not in capsys.readouterr().out


def test_t63_cli_errors_never_print_the_connection_string_or_password(
    eraser_url: str,
    world: World,
    storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Red when: a driver error (host, login, password) reaches the terminal or the logs (ADR-0013).
    secret = "s3cr3t-eraser-pw"
    head, tail = eraser_url.rsplit("@", 1)
    bad = f"{head.rsplit(':', 1)[0]}:{secret}@{tail}"
    monkeypatch.setenv("CORE_ERASER_DATABASE_URL", bad)
    status = cli.main(["erase-user", "--user-id", str(world.user_id), "--confirm-email", "x@y.z"])
    captured = capsys.readouterr()
    assert status == 2
    assert "OperationalError" in captured.err
    assert secret not in captured.out + captured.err + caplog.text


def test_t63_cli_errors_never_print_the_login_or_the_host(
    eraser_url: str,
    eraser_engine: Engine,
    world: World,
    storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Red when: the driver's message is printed; it names the login and the server (ADR-0013),
    # even though it never carries the password itself.
    head, tail = eraser_url.rsplit("@", 1)
    monkeypatch.setenv("CORE_ERASER_DATABASE_URL", f"{head.rsplit(':', 1)[0]}:wrong-pw@{tail}")
    status = cli.main(["erase-user", "--user-id", str(world.user_id), "--confirm-email", "x@y.z"])
    err = capsys.readouterr().err
    assert status == 2
    login, host = eraser_engine.url.username, eraser_engine.url.host
    assert login and host
    assert login not in err and host not in err
