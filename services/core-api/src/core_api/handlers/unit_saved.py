"""The review question of a saved card (T7.9, US-02b AC11, US-06).

`unit.saved.v1` goes to ai-service, which holds no card text, so the question is asked the other
way: core-api sends the card to `POST /v1/review-question` from a background job and stores the
answer. `ensure_review_question` is that step, idempotent:

- A card with no active review question gets one (one model call), at Save.
- A card whose question was written from the current revision gets nothing (a second Save, a
  repeated job: no duplicate, no call).
- A card edited since (a newer revision) keeps its old question. A new one is made only when
  `lazy` is set, which is when the card is due; never at the edit.
- The cap or the model being down (`pending_ai`) is not an error: the card still enters review
  with the question it has, or without, and a later run makes it.

The question carries its rubric and reference answer, so grading never resends the anchors.
Logs hold ids and rule names, never the card's text or the model's (ADR-0013).
"""

import logging
import uuid
from typing import Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.clients.ai_client import NotGraded
from core_api.clients.review_question_contract import ReviewQuestionReply
from core_api.db.models import Anchor, KnowledgeUnit, Question, QuestionUnit, UnitRevision
from core_api.domain.question_hash import content_hash

_log = logging.getLogger("core_api.handlers")

Outcome = Literal["created", "current", "kept", "skipped", "pending_ai", "failed"]
MAX_QUOTES = 5
MAX_QUOTE_CHARS = 1000
MAX_SUMMARY_CHARS = 1000


class AiUnavailableError(Exception):
    """ai-service did not answer: the job is retried."""


class ReviewQuestionAi(Protocol):
    def review_question(self, payload: dict[str, object]) -> ReviewQuestionReply | NotGraded: ...


def _locked_unit(session: Session, user_id: uuid.UUID, unit_id: uuid.UUID) -> KnowledgeUnit | None:
    """The card, locked: two jobs for one card take turns, so the second finds the question."""
    return session.scalars(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.id == unit_id, KnowledgeUnit.user_id == user_id)
        .with_for_update()
    ).one_or_none()


def latest_question_rev(session: Session, user_id: uuid.UUID, unit_id: uuid.UUID) -> int | None:
    """The newest revision an active review question of this card was written from (a question
    from before revisions counts as 0), or None when it has none."""
    rows = session.scalars(
        select(func.coalesce(Question.unit_rev, 0))
        .join(QuestionUnit, QuestionUnit.question_id == Question.id)
        .where(
            QuestionUnit.unit_id == unit_id,
            QuestionUnit.user_id == user_id,
            Question.user_id == user_id,
            Question.source == "review_auto",
            Question.status == "active",
        )
    ).all()
    return max(rows, default=None)


def _payload(session: Session, user_id: uuid.UUID, unit: KnowledgeUnit) -> dict[str, object]:
    quotes = session.scalars(
        select(Anchor.quote_text)
        .where(Anchor.unit_id == unit.id, Anchor.user_id == user_id)
        .order_by(Anchor.created_at, Anchor.id)
        .limit(MAX_QUOTES)
    ).all()
    return {
        "user_id": str(user_id),
        "subject_id": str(unit.subject_id),
        "unit_id": str(unit.id),
        "title": unit.title,
        "summary": unit.summary[:MAX_SUMMARY_CHARS],
        "quotes": [q[:MAX_QUOTE_CHARS] for q in quotes],
    }


def ensure_review_question(
    session: Session,
    user_id: uuid.UUID,
    unit_id: uuid.UUID,
    ai: ReviewQuestionAi,
    *,
    lazy: bool,
) -> Outcome:
    """Make sure the card has a review question for its current revision, as above. The caller
    commits. Raises `AiUnavailableError` when ai-service cannot be reached (the job retries)."""
    unit = _locked_unit(session, user_id, unit_id)
    if unit is None or unit.status != "canonical" or unit.retired_at is not None:
        return "skipped"
    rev = session.scalar(
        select(func.max(UnitRevision.rev)).where(
            UnitRevision.unit_id == unit.id, UnitRevision.user_id == user_id
        )
    )
    if rev is None:
        return "skipped"
    have = latest_question_rev(session, user_id, unit.id)
    if have is not None and have >= rev:
        return "current"
    if have is not None and not lazy:
        return "kept"
    reply = ai.review_question(_payload(session, user_id, unit))
    extra = {"unit_id": str(unit.id), "unit_rev": rev}
    if isinstance(reply, NotGraded):
        if reply.failure == "unavailable":
            raise AiUnavailableError(reply.reason)
        _log.warning("review question not made", extra=extra | {"outcome": reply.reason})
        return "pending_ai" if reply.failure == "quota" else "failed"
    if reply.status != "ok" or not (reply.prompt and reply.reference_answer and reply.rubric):
        outcome: Outcome = "pending_ai" if reply.status == "pending_ai" else "failed"
        _log.warning("review question not made", extra=extra | {"outcome": reply.failure})
        return outcome
    _store(session, user_id, unit, rev, reply)
    _log.info("review question made", extra=extra)
    return "created"


def _store(
    session: Session, user_id: uuid.UUID, unit: KnowledgeUnit, rev: int, reply: ReviewQuestionReply
) -> None:
    """One active question of this card, linked to it. The same wording as an active question of
    the subject (the hash is unique among active ones) is that question: it is linked and moved
    to this revision, never doubled."""
    assert reply.prompt and reply.reference_answer and reply.rubric
    question = session.scalars(
        select(Question).where(
            Question.user_id == user_id,
            Question.subject_id == unit.subject_id,
            Question.content_hash == content_hash(reply.prompt),
            Question.status == "active",
        )
    ).one_or_none()
    if question is None:
        question = Question(
            user_id=user_id,
            subject_id=unit.subject_id,
            level=1,
            prompt=reply.prompt,
            reference_answer=reply.reference_answer,
            rubric=reply.rubric,
            status="active",
            content_hash=content_hash(reply.prompt),
            run_id=reply.run_id,
            source="review_auto",
            unit_rev=rev,
        )
        session.add(question)
        session.flush()
    else:
        question.unit_rev = max(question.unit_rev or 0, rev)
    linked = session.scalar(
        select(func.count())
        .select_from(QuestionUnit)
        .where(QuestionUnit.question_id == question.id, QuestionUnit.unit_id == unit.id)
    )
    if not linked:
        session.add(
            QuestionUnit(
                user_id=user_id,
                subject_id=unit.subject_id,
                question_id=question.id,
                unit_id=unit.id,
            )
        )
    session.flush()
