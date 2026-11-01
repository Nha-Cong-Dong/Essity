"""The `regenerate_review_question` job (T7.9, US-02b AC11): make the review question of one card.

Two callers, one job: Save enqueues it for every card it saves (`lazy` false: a card with no
question gets one), and the review session builder enqueues it for a due card whose question is
older than its revision (`lazy` true: a new question at the moment it is needed, never at the
edit). See `handlers.unit_saved.ensure_review_question` for the rules. Delivery is at least
once and the step is idempotent. ai-service unreachable raises, so the job is retried; the cap
or a model that broke its rules ends the job without error.
"""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from core_api.clients.ai_client import AiServiceClient
from core_api.config import get_settings
from core_api.db.engine import get_engine
from core_api.handlers.unit_saved import ReviewQuestionAi, ensure_review_question
from core_api.jobs.handler import job_handler
from core_api.jobs.queue import enqueue_job

REGENERATE_REVIEW_QUESTION = "regenerate_review_question"

_log = logging.getLogger("core_api.jobs")


def enqueue_review_question(
    session: Session, user_id: uuid.UUID, unit_id: uuid.UUID, *, lazy: bool
) -> None:
    """Add the job in the caller's transaction."""
    enqueue_job(
        session,
        REGENERATE_REVIEW_QUESTION,
        {"user_id": str(user_id), "unit_id": str(unit_id), "lazy": lazy},
    )


def run(payload: dict[str, Any], ai: ReviewQuestionAi) -> str:
    user_id, unit_id = uuid.UUID(payload["user_id"]), uuid.UUID(payload["unit_id"])
    with Session(get_engine()) as session:
        outcome = ensure_review_question(
            session, user_id, unit_id, ai, lazy=bool(payload.get("lazy", False))
        )
        session.commit()
    return outcome


@job_handler(REGENERATE_REVIEW_QUESTION)
def regenerate_review_question(payload: dict[str, Any]) -> None:
    client = AiServiceClient.from_settings(get_settings())
    try:
        outcome = run(payload, client)
    finally:
        client.close()
    _log.info("review question job done", extra={"outcome": outcome})
