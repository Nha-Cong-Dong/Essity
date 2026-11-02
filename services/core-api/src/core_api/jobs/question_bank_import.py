"""The `question_bank_import` job (T8.1c, US-14 AC9): an import that stopped for lack of an AI turn
was queued by the route (`handlers.question_bank_import.enqueue_import`); this job runs it again.

It uses the durable job queue the review-question job uses, so a queued import survives a restart
and needs no table of its own. Each run does exactly what the route does (`run_import`):

- no turn (limit, quota, model down): nothing is stored and the job is queued again 10 minutes
  later; a bank is never half-saved;
- a job older than `MAX_AGE` (as T8.4b's grading), or whose account, subject or bank is gone, or
  whose file can no longer be read, ends without a call to the AI;
- a stored bank is skipped by hash, so a job delivered twice adds nothing.

Logs hold ids and counts, never a question or answer (ADR-0013).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.orm import Session

from core_api.api.attempts import GRADINGS_PER_USER
from core_api.clients.ai_client import AiServiceClient
from core_api.clients.redis import get_redis
from core_api.clients.storage import ObjectStorage, S3Storage
from core_api.config import get_settings
from core_api.db.engine import get_engine
from core_api.db.models import Document, User
from core_api.handlers.question_bank_import import (
    QUESTION_BANK_IMPORT,
    BankAi,
    BankPagesError,
    enqueue_import,
    run_import,
)
from core_api.jobs.handler import job_handler
from core_api.repositories.document import DocumentRepository
from core_api.repositories.subject import SubjectRepository
from core_api.security.rate_limit import (
    RateLimit,
    RateLimitedError,
    RateLimiter,
    RateLimiterUnavailableError,
)

# A bank that has waited this long is given up; the learner can import it again by hand.
MAX_AGE = timedelta(days=7)

_log = logging.getLogger("core_api.jobs")

__all__ = ["MAX_AGE", "QUESTION_BANK_IMPORT", "run_queued"]


class Limiter(Protocol):
    def enforce(self, rule: RateLimit, key: str) -> None: ...


def run_queued(
    session: Session,
    payload: dict[str, Any],
    ai: BankAi,
    storage: ObjectStorage,
    limiter: Limiter,
    now: datetime,
) -> str:
    """One run. Returns `done`, `requeued` or `dropped`; the caller commits."""
    try:
        user_id = uuid.UUID(payload["user_id"])
        subject_id = uuid.UUID(payload["subject_id"])
        document_id = uuid.UUID(payload["document_id"])
        queued_at = datetime.fromisoformat(payload["queued_at"])
    except (KeyError, ValueError, TypeError):
        return "dropped"
    if now - queued_at > MAX_AGE:
        return "dropped"
    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return "dropped"
    document = DocumentRepository(session, user_id).get(document_id)
    if (
        document is None
        or document.subject_id != subject_id
        or document.role != "question_bank"
        or document.status != "indexed"
        or SubjectRepository(session, user_id).get(subject_id) is None
    ):
        return "dropped"

    def may_call() -> bool:
        try:
            limiter.enforce(GRADINGS_PER_USER, str(user_id))
        except (RateLimitedError, RateLimiterUnavailableError):
            return False
        return True

    try:
        result = run_import(session, user_id, document, ai, storage, may_call)
    except BankPagesError as error:
        if error.http == 503:  # storage is down for now: try later
            return _again(session, user_id, document, queued_at)
        return "dropped"
    if result.status == "pending_ai":
        return _again(session, user_id, document, queued_at)
    _log.info(
        "question bank import done",
        extra={"outcome": result.status, "count": result.added},
    )
    return "done"


def _again(session: Session, user_id: uuid.UUID, document: Document, queued_at: datetime) -> str:
    enqueue_import(session, user_id, document, queued_at=queued_at, delayed=True)
    return "requeued"


@job_handler(QUESTION_BANK_IMPORT)
def question_bank_import(payload: dict[str, Any]) -> None:
    settings = get_settings()
    ai = AiServiceClient.from_settings(settings)
    try:
        with Session(get_engine()) as session:
            outcome = run_queued(
                session,
                payload,
                ai,
                S3Storage.from_settings(settings),
                RateLimiter(get_redis()),
                datetime.now(UTC),
            )
            session.commit()
    finally:
        ai.close()
    _log.info("question bank import job", extra={"outcome": outcome})
