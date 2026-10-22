"""T1.5: sending email. SMTP tests use the Compose Mailpit (CI: a Mailpit service container)."""

import io
import json
import logging
import os
import ssl
import uuid
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest

from core_api.clients.email.sender import EmailMessage, InMemoryEmailSender
from core_api.clients.email.smtp import SmtpEmailSender, smtp_sender_from_settings
from core_api.clients.email.templates import EmailTemplate, render_email
from core_api.config import Settings
from core_api.logging import configure_logging

MAILPIT_SMTP_HOST = os.environ.get("CORE_TEST_SMTP_HOST", "127.0.0.1")
MAILPIT_SMTP_PORT = int(os.environ.get("CORE_TEST_SMTP_PORT", "1025"))
MAILPIT_API = os.environ.get("CORE_TEST_MAILPIT_API", "http://127.0.0.1:8025")
LINK = "https://essity.example/verify?token=token-that-must-not-be-logged"


def recipient() -> str:
    # Unique per test: Mailpit is shared, and tests run in any order.
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def mailpit_message(to: str) -> dict[str, Any]:
    found = httpx2.get(f"{MAILPIT_API}/api/v1/search", params={"query": f"to:{to}"}).json()
    [summary] = found["messages"]
    return httpx2.get(f"{MAILPIT_API}/api/v1/message/{summary['ID']}").json()


@pytest.fixture
def log_output() -> Iterator[io.StringIO]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("core-api", "INFO", stream=buffer)
    yield buffer
    root.handlers, root.level = saved


# --- Templates -------------------------------------------------------------------------------


@pytest.mark.parametrize("template", list(EmailTemplate))
def test_every_template_renders_a_subject_and_a_body(template: EmailTemplate) -> None:
    subject, body = render_email(
        template,
        link=LINK,
        login_link="https://essity.example/login",
        reset_link="https://essity.example/forgot",
        valid_for="24 giờ",
    )
    assert subject and "\n" not in subject
    assert body.startswith("Chào bạn,")
    assert "$" not in subject + body  # every placeholder was filled


def test_verify_email_carries_the_link_and_how_long_it_lasts() -> None:
    _, body = render_email(EmailTemplate.VERIFY_EMAIL, link=LINK, valid_for="24 giờ")
    assert LINK in body
    assert "24 giờ" in body


def test_account_exists_email_offers_login_and_reset_not_a_new_account() -> None:
    # ADR-0014: sign-up never reveals an existing account on screen; the owner learns it here.
    _, body = render_email(
        EmailTemplate.ACCOUNT_EXISTS,
        login_link="https://essity.example/login",
        reset_link="https://essity.example/forgot",
    )
    assert "https://essity.example/login" in body
    assert "https://essity.example/forgot" in body


def test_missing_value_is_an_error_not_a_blank_in_the_email() -> None:
    with pytest.raises(KeyError):
        render_email(EmailTemplate.VERIFY_EMAIL, valid_for="24 giờ")


# --- Senders ---------------------------------------------------------------------------------


def test_in_memory_sender_keeps_what_was_sent() -> None:
    sender = InMemoryEmailSender()
    message = EmailMessage(to="alice@example.com", subject="Xin chào", text="Nội dung")
    sender.send(message)
    assert sender.sent == [message]


def test_smtp_sender_delivers_to_mailpit_in_utf8() -> None:
    to = recipient()
    subject, body = render_email(EmailTemplate.VERIFY_EMAIL, link=LINK, valid_for="24 giờ")
    SmtpEmailSender(
        host=MAILPIT_SMTP_HOST, port=MAILPIT_SMTP_PORT, from_address="no-reply@essity.test"
    ).send(EmailMessage(to=to, subject=subject, text=body))

    delivered = mailpit_message(to)
    assert delivered["Subject"] == subject  # Vietnamese subject survives the encoding
    assert delivered["From"]["Address"] == "no-reply@essity.test"
    assert LINK in delivered["Text"]


def test_smtp_sender_logs_the_masked_address_and_never_the_body(log_output: io.StringIO) -> None:
    to = recipient()
    SmtpEmailSender(
        host=MAILPIT_SMTP_HOST, port=MAILPIT_SMTP_PORT, from_address="no-reply@essity.test"
    ).send(EmailMessage(to=to, subject="Xác minh email", text=f"Link: {LINK}"))

    lines = [json.loads(line) for line in log_output.getvalue().splitlines()]
    [sent] = [line for line in lines if line["message"] == "email sent"]
    assert sent["email"] == f"{to[0]}***@example.com"
    raw = log_output.getvalue()
    assert to not in raw
    assert LINK not in raw


def test_sender_from_settings_uses_the_configured_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORE_SMTP_HOST", "mailpit")
    monkeypatch.setenv("CORE_SMTP_PORT", "2525")
    monkeypatch.setenv("CORE_EMAIL_FROM", "no-reply@essity.test")
    sender = smtp_sender_from_settings(Settings())  # pyright: ignore[reportCallIssue]
    assert (sender.host, sender.port, sender.from_address) == (
        "mailpit",
        2525,
        "no-reply@essity.test",
    )
    assert sender.username is None and not sender.starttls


class _FakeSmtp:
    """smtplib.SMTP stand-in that records what the sender asks of it."""

    calls: list[tuple[str, object]] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        _FakeSmtp.calls = []

    def __enter__(self) -> "_FakeSmtp":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def starttls(self, context: object = None) -> None:
        _FakeSmtp.calls.append(("starttls", context))

    def login(self, username: str, _password: str) -> None:
        _FakeSmtp.calls.append(("login", username))

    def send_message(self, _mime: object) -> None:
        _FakeSmtp.calls.append(("send", None))


def test_r04_starttls_checks_the_server_certificate_and_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: starttls() runs without a verifying context. smtplib's default does not check
    # the certificate or the host name, so anyone in between reads the password and the links
    # (review f617e23).
    monkeypatch.setattr("core_api.clients.email.smtp.smtplib.SMTP", _FakeSmtp)
    sender = SmtpEmailSender(
        "smtp.essity.example",
        587,
        "no-reply@essity.example",
        username="essity",
        password="smtp-password",
        starttls=True,
    )
    sender.send(EmailMessage(to="a@example.com", subject="s", text="t"))
    kind, context = _FakeSmtp.calls[0]
    assert kind == "starttls"
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert [call[0] for call in _FakeSmtp.calls] == ["starttls", "login", "send"]
