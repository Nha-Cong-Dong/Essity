"""T1.5: the `send_email` job, end to end through a real worker and Mailpit.

The payload names the user and the kind of email, nothing else (ADR-0018): `procrastinate_jobs`
keeps job arguments after the job is done, so an address or a link with a token must never be
in it. The handler reads the address from the database when it runs.
"""

import io
import json
import logging
import os
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.clients.email.sender import EmailMessage
from core_api.db.models import User
from core_api.jobs import send_email
from core_api.jobs.send_email import EmailKind, enqueue_email
from core_api.logging import configure_logging
from core_api.repositories.user import UserRepository

MAILPIT_SMTP_HOST = os.environ.get("CORE_TEST_SMTP_HOST", "127.0.0.1")
MAILPIT_SMTP_PORT = os.environ.get("CORE_TEST_SMTP_PORT", "1025")
MAILPIT_API = os.environ.get("CORE_TEST_MAILPIT_API", "http://127.0.0.1:8025")
WEB_BASE_URL = "https://essity.example"

pytestmark = pytest.mark.usefixtures("clean_jobs")


@pytest.fixture(autouse=True)
def email_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORE_SMTP_HOST", MAILPIT_SMTP_HOST)
    monkeypatch.setenv("CORE_SMTP_PORT", MAILPIT_SMTP_PORT)
    monkeypatch.setenv("CORE_WEB_BASE_URL", WEB_BASE_URL)


@pytest.fixture
def user(engine: Engine) -> Iterator[User]:
    """A committed user with an address unique to the test (Mailpit is shared)."""
    with Session(engine, expire_on_commit=False) as session:
        created = UserRepository(session).create(f"user-{uuid.uuid4().hex[:12]}@example.com")
        session.commit()
    yield created
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": created.id})


def enqueue_committed(engine: Engine, user_id: uuid.UUID, kind: EmailKind) -> None:
    with Session(engine) as session:
        enqueue_email(session, user_id, kind)
        session.commit()


def job_rows(engine: Engine) -> list[dict[str, Any]]:
    query = text("SELECT status::text, attempts, args FROM procrastinate_jobs ORDER BY id")
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


def mailpit_messages(to: str) -> list[dict[str, Any]]:
    found = httpx2.get(f"{MAILPIT_API}/api/v1/search", params={"query": f"to:{to}"}).json()
    return [
        httpx2.get(f"{MAILPIT_API}/api/v1/message/{summary['ID']}").json()
        for summary in found["messages"]
    ]


@pytest.fixture
def log_output() -> Iterator[Callable[[], str]]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("core-worker", "DEBUG", stream=buffer)
    yield buffer.getvalue
    root.handlers, root.level = saved


def test_account_exists_email_reaches_mailpit(
    engine: Engine, work: Callable[..., None], user: User
) -> None:
    enqueue_committed(engine, user.id, EmailKind.ACCOUNT_EXISTS)
    work()

    [message] = mailpit_messages(user.email)
    assert message["Subject"] == "Bạn đã có tài khoản Essity"
    assert f"{WEB_BASE_URL}/login" in message["Text"]
    assert f"{WEB_BASE_URL}/forgot-password" in message["Text"]
    assert [row["status"] for row in job_rows(engine)] == ["succeeded"]


def test_payload_holds_the_user_id_and_the_kind_only(engine: Engine, user: User) -> None:
    # ADR-0018: the job table keeps arguments, so no address and no secret go in them.
    enqueue_committed(engine, user.id, EmailKind.ACCOUNT_EXISTS)
    [row] = job_rows(engine)
    assert row["args"] == {"payload": {"user_id": str(user.id), "email": "account_exists"}}
    assert user.email not in json.dumps(row["args"])


def test_no_email_for_a_user_deleted_before_the_job_ran(
    engine: Engine, work: Callable[..., None], user: User
) -> None:
    enqueue_committed(engine, user.id, EmailKind.ACCOUNT_EXISTS)
    with engine.begin() as connection:
        connection.execute(
            text('UPDATE "user" SET deleted_at = :now WHERE id = :id'),
            {"now": datetime.now(UTC), "id": user.id},
        )
    work()

    assert mailpit_messages(user.email) == []
    assert [row["status"] for row in job_rows(engine)] == ["succeeded"]  # nothing to retry


def test_no_email_for_a_user_that_no_longer_exists(
    engine: Engine, work: Callable[..., None]
) -> None:
    enqueue_committed(engine, uuid.uuid4(), EmailKind.ACCOUNT_EXISTS)
    work()
    assert [row["status"] for row in job_rows(engine)] == ["succeeded"]


def test_failed_delivery_is_retried(
    engine: Engine, work: Callable[..., None], user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DownSender:
        def send(self, message: EmailMessage) -> None:
            raise ConnectionRefusedError("smtp is down")

    monkeypatch.setattr(send_email, "email_sender", DownSender)
    enqueue_committed(engine, user.id, EmailKind.ACCOUNT_EXISTS)
    work()

    [row] = job_rows(engine)
    assert (row["status"], row["attempts"]) == ("todo", 1)  # scheduled again (T1.4 backoff)


def test_logs_carry_the_masked_address_and_never_the_body(
    engine: Engine, work: Callable[..., None], user: User, log_output: Callable[[], str]
) -> None:
    # US-12 AC8: no address in clear, no link (links carry tokens from T1.7 on).
    enqueue_committed(engine, user.id, EmailKind.ACCOUNT_EXISTS)
    work()

    output = log_output()
    local_part = user.email.split("@")[0]
    assert local_part not in output
    assert WEB_BASE_URL not in output
    sent = next(json.loads(line) for line in output.splitlines() if '"email sent"' in line)
    assert sent["email"] == f"{local_part[0]}***@example.com"
