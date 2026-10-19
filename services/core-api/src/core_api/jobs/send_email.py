"""The `send_email` job (T1.5): emails to a user, sent by the worker, never by a request.

The payload is the user's id and the kind of email, nothing else (ADR-0018): job arguments stay
in `procrastinate_jobs` after the job is done, so no address, link or token goes in them. The
handler reads the address when it runs and builds any link itself; T1.7 adds the verification
email, whose handler creates the token and stores only its hash.

Delivery is at least once: a retry after a lost acknowledgement sends the email again. That is
harmless for the kinds here.
"""

import logging
import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from core_api.clients.email.sender import EmailMessage, EmailSender
from core_api.clients.email.smtp import smtp_sender_from_settings
from core_api.clients.email.templates import EmailTemplate, render_email
from core_api.config import Settings, get_settings
from core_api.db.engine import get_engine
from core_api.jobs.handler import job_handler
from core_api.jobs.queue import enqueue_job
from core_api.repositories.user import UserRepository

SEND_EMAIL = "send_email"

_log = logging.getLogger("core_api.jobs")


class EmailKind(StrEnum):
    ACCOUNT_EXISTS = "account_exists"  # sign-up with an address that already has an account


def enqueue_email(session: Session, user_id: uuid.UUID, kind: EmailKind) -> None:
    """Send `kind` to the user once `session`'s transaction commits."""
    enqueue_job(session, SEND_EMAIL, {"user_id": str(user_id), "email": EmailKind(kind).value})


def email_sender() -> EmailSender:
    return smtp_sender_from_settings(get_settings())


@job_handler(SEND_EMAIL)
def send_email(payload: dict[str, Any]) -> None:
    kind = EmailKind(payload["email"])
    settings = get_settings()
    with Session(get_engine()) as session:
        user = UserRepository(session).get(uuid.UUID(payload["user_id"]))
        if user is None or user.deleted_at is not None:
            # Deleted since the job was queued: nothing to send, nothing to retry.
            _log.info("email skipped", extra={"job_kind": SEND_EMAIL, "outcome": "skipped"})
            return
        message = _compose(kind, user.email, settings)
    email_sender().send(message)


def _compose(kind: EmailKind, to: str, settings: Settings) -> EmailMessage:
    base = settings.web_base_url.rstrip("/")
    match kind:
        case EmailKind.ACCOUNT_EXISTS:
            subject, text = render_email(
                EmailTemplate.ACCOUNT_EXISTS,
                login_link=f"{base}/login",
                reset_link=f"{base}/forgot-password",
            )
    return EmailMessage(to=to, subject=subject, text=text)
