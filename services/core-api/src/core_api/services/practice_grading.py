"""Grading a practice attempt (T8.4, US-05 AC9-AC14, US-16 AC5/AC10/AC11, ADR-0029).

The attempt is already submitted and committed by the caller (the answer is never lost to a failed
grading). Then, in the caller's transaction and under the attempt's grading lock:

1. a grade that exists is returned as it is: "Chấm lại" never asks the AI twice, and the schedule
   moves once per grade (`record_grade` is idempotent per grade);
2. "Không nhớ" is graded by the system, without the AI;
3. otherwise ai-service gets question, rubric, a short reference answer and the learner's answer,
   nothing else (AC11); a rubric or reference that is missing fails closed without a call;
4. `Grade` and `record_grade` (the question's own FSRS schedule) are written together, or neither.

A practice grade never touches `review_log` or `memory_state` (US-16 AC11). When the AI is out of
turns or down, the answer stays saved and the outcome is `pending` (neutral copy on screen).
Nothing here logs or raises with the learner's answer in it (ADR-0013).
"""

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from sqlalchemy import update
from sqlalchemy.orm import Session

from core_api.clients.ai_client import NotGraded
from core_api.clients.practice_contract import DraftAnswerReply, PracticeGradeReply
from core_api.db.models import Attempt, Grade, Question, QuestionType
from core_api.domain.mastery import PracticeVerdict, reference_seconds
from core_api.domain.scheduling.rating import Verdict
from core_api.repositories.practice_attempt import (
    AttemptNotDraftError,
    AttemptNotFoundError,
    PracticeAttemptRepository,
)
from core_api.repositories.question import QuestionNotFoundError, QuestionUnitRepository
from core_api.repositories.review import GradeRepository
from core_api.services.practice import record_grade

_log = logging.getLogger(__name__)

Grading = Literal["graded", "pending", "failed", "in_progress"]
MAX_RUBRIC_IDEAS = 8
MAX_DRAFT_CARDS = 6


class PracticeAi(Protocol):
    def grade_practice(self, payload: dict[str, object]) -> PracticeGradeReply | NotGraded: ...

    def draft_answer(self, payload: dict[str, object]) -> DraftAnswerReply | NotGraded: ...


@dataclass(frozen=True)
class PracticeOutcome:
    grading: Grading
    grade: Grade | None = None
    failure: str | None = None


class GradeNotFoundError(LookupError):
    """No such practice grade for this user."""


class GradeNotCurrentError(ValueError):
    """The grade is not the attempt's newest."""


class GradeBusyError(ValueError):
    """The attempt is being graded or overridden by another request."""


def rubric_of(question: Question) -> list[str] | None:
    """The question's rubric as a list of ideas, or None when it has none usable. A rubric stored
    as one string is one idea; anything else that is not a list of text is unusable."""
    raw: Any = question.rubric
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return None
    ideas = [item.strip() for item in raw if isinstance(item, str) and item.strip()]  # pyright: ignore[reportUnknownVariableType]
    if not ideas or len(ideas) != len(raw):  # pyright: ignore[reportUnknownArgumentType]
        return None
    return ideas[:MAX_RUBRIC_IDEAS]


def standard_answer(question: Question) -> str | None:
    """The answer the learner is graded against: the bank's, the learner's own fix, or the AI's
    draft (`answer_text`); an old review question has only `reference_answer`."""
    if question.answer_text is not None:
        return question.answer_text
    if question.source == "review_auto":
        return question.reference_answer
    return None


def reference_time(session: Session, question: Question, ideas: int) -> float:
    """Seconds an answer should take: the question type's, else the default per idea (T8.6)."""
    if question.type_id is not None:
        found = session.get(QuestionType, question.type_id)
        if found is not None and found.user_id == question.user_id:
            return float(found.ref_time_s)
    return reference_seconds(ideas, [])


def ensure_reference(
    session: Session, user_id: uuid.UUID, question: Question, ai: PracticeAi
) -> bool:
    """Make the question ready: a bank question with no answer gets an AI-drafted one
    (`answer_origin = ai`, AC13), once. Failure leaves the question as it was, still usable.
    True when the question has an answer afterwards."""
    if standard_answer(question) is not None:
        return True
    units = QuestionUnitRepository(session, user_id).units_of(question.id)
    cards: list[dict[str, object]] = [
        {"card_id": str(u.id), "text": f"{u.title}: {u.summary}"[:1500]}
        for u in units[:MAX_DRAFT_CARDS]
    ]
    reply = ai.draft_answer(
        {
            "user_id": str(user_id),
            "subject_id": str(question.subject_id),
            "question": question.prompt,
            "cards": cards,
        }
    )
    if isinstance(reply, NotGraded) or reply.status != "ok" or not reply.answer:
        return False
    # Only while still empty: a learner's fix or a concurrent draft is never overwritten.
    session.execute(
        update(Question)
        .where(
            Question.user_id == user_id, Question.id == question.id, Question.answer_text.is_(None)
        )
        .values(answer_text=reply.answer, answer_origin="ai")
        .execution_options(synchronize_session="fetch")
    )
    session.refresh(question)
    return standard_answer(question) is not None


def _verdicts(verdict: Verdict, units: Sequence[uuid.UUID]) -> dict[uuid.UUID, Verdict]:
    """One row per unit the question checks (a practice grade judges the question as a whole)."""
    each = Verdict.INCORRECT if verdict == Verdict.FORGOT else verdict
    return dict.fromkeys(units, each)


def _practice_verdict(verdict: Verdict) -> PracticeVerdict:
    match verdict:
        case Verdict.CORRECT:
            return "correct"
        case Verdict.PARTIAL:
            return "partial"
        case _:
            return "incorrect"  # "Không nhớ" counts as wrong in the schedule


def _write(
    session: Session,
    user_id: uuid.UUID,
    attempt: Attempt,
    question: Question,
    *,
    source: str,
    verdict: Verdict,
    run_id: uuid.UUID | None,
    missing: Sequence[str] = (),
    anchors: Sequence[str] = (),
    ref_seconds: float,
) -> Grade:
    """Grade and schedule together, in the caller's transaction (T8.3 review F3/Y4)."""
    units = [u.id for u in QuestionUnitRepository(session, user_id).units_of(question.id)]
    grade = GradeRepository(session, user_id).add_with_units(
        attempt.id,
        source=source,
        overall=verdict,
        understanding=None,  # the 1-3 scale belongs to cards (US-05 §9 #9)
        units=_verdicts(verdict, units),
        run_id=run_id,
        missing=missing,
        anchors_used=anchors,
    )
    assert attempt.active_ms is not None and attempt.timing_ok is not None  # set at submit
    record_grade(
        session,
        user_id,
        question.id,
        grade.id,
        verdict=_practice_verdict(verdict),
        active_seconds=attempt.active_ms / 1000,
        reference_seconds=ref_seconds,
        timing_ok=attempt.timing_ok,
    )
    return grade


def _load(session: Session, user_id: uuid.UUID, attempt_id: uuid.UUID) -> tuple[Attempt, Question]:
    attempt = PracticeAttemptRepository(session, user_id).get_practice(attempt_id)
    if attempt is None:
        raise AttemptNotFoundError(attempt_id)
    if attempt.status != "submitted":
        raise AttemptNotDraftError(attempt_id)  # not submitted yet
    question = session.get(Question, attempt.question_id)
    if question is None or question.user_id != user_id:
        raise QuestionNotFoundError(attempt.question_id)
    return attempt, question


def grade_practice_attempt(
    session: Session,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    ai: PracticeAi,
    *,
    may_call_ai: Callable[[], bool],
) -> PracticeOutcome:
    """Grade a submitted practice attempt once. `AttemptNotFoundError` for another user's or a
    review attempt; `AttemptNotDraftError` when it is not submitted yet."""
    attempt, question = _load(session, user_id, attempt_id)
    grades = GradeRepository(session, user_id)
    if not grades.try_lock_attempt(attempt.id):
        return PracticeOutcome("in_progress")
    current = grades.latest_for_attempt(attempt.id)
    if current is not None:
        return PracticeOutcome("graded", current)
    ideas = rubric_of(question)
    ref_seconds = reference_time(session, question, len(ideas or []))
    if attempt.dont_remember:
        grade = _write(
            session,
            user_id,
            attempt,
            question,
            source="system",
            verdict=Verdict.FORGOT,
            run_id=None,
            ref_seconds=ref_seconds,
        )
        return PracticeOutcome("graded", grade)
    reference = standard_answer(question)
    if ideas is None or reference is None or not attempt.answer_text.strip():
        return PracticeOutcome("failed", failure="not_ready")  # fail closed, no AI call
    if not may_call_ai():
        return PracticeOutcome("pending")
    reply = ai.grade_practice(
        {
            "user_id": str(user_id),
            "subject_id": str(question.subject_id),
            "question": question.prompt,
            "rubric": ideas,
            "reference_answer": reference,
            "answer": attempt.answer_text,
        }
    )
    if isinstance(reply, NotGraded):
        return PracticeOutcome(
            "pending" if reply.failure in ("unavailable", "quota") else "failed",
            failure=reply.failure,
        )
    if reply.status == "pending_ai":
        return PracticeOutcome("pending")
    if reply.status != "ok" or reply.overall is None or len(reply.ideas) != len(ideas):
        return PracticeOutcome("failed", failure="invalid")
    missing = [
        idea for idea, got in zip(ideas, reply.ideas, strict=True) if got.verdict != "correct"
    ]
    anchors = [got.anchor for got in reply.ideas if got.anchor]
    grade = _write(
        session,
        user_id,
        attempt,
        question,
        source="ai",
        verdict=Verdict(reply.overall),
        run_id=reply.run_id,
        missing=missing,
        anchors=anchors,
        ref_seconds=ref_seconds,
    )
    return PracticeOutcome("graded", grade)


def override_practice_grade(
    session: Session,
    user_id: uuid.UUID,
    grade_id: uuid.UUID,
    choice: Literal["correct", "incorrect"],
) -> Grade:
    """ "Chấm sai" (US-09, US-16 AC10): a new `user_override` grade and a new `practice_log` row for
    it, then the schedule rebuilt from the log. The machine's grade stays. Never touches
    `review_log` or `memory_state`."""
    grades = GradeRepository(session, user_id)
    grade = grades.get(grade_id)
    if grade is None:
        raise GradeNotFoundError(grade_id)
    attempt, question = _load_for_grade(session, user_id, grade)
    if not grades.try_lock_attempt(attempt.id):
        raise GradeBusyError(attempt.id)
    current = grades.latest_for_attempt(attempt.id)
    assert current is not None
    if current.overall == choice and (current.id == grade.id or current.source == "user_override"):
        return current
    if current.id != grade.id:
        raise GradeNotCurrentError(grade_id)
    ideas = rubric_of(question)
    return _write(
        session,
        user_id,
        attempt,
        question,
        source="user_override",
        verdict=Verdict(choice),
        run_id=None,
        ref_seconds=reference_time(session, question, len(ideas or [])),
    )


def _load_for_grade(session: Session, user_id: uuid.UUID, grade: Grade) -> tuple[Attempt, Question]:
    try:
        return _load(session, user_id, grade.attempt_id)
    except (AttemptNotFoundError, AttemptNotDraftError) as error:
        raise GradeNotFoundError(grade.id) from error  # a review grade: not ours
