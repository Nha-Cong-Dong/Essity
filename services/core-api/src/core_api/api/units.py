"""`POST` and `DELETE /v1/units/{id}/skip` (T2.23, US-04 AC5, US-03 AC8): "Không cần ôn phần này"
and its undo. A skip writes `skipped_at` only: schedule and history stay (ADR-0008).

In an open session, the questions the skip takes away are replaced by others (`compose_today`
over the session's subject, without the questions already in it) so the session keeps its size;
the replacements go after the last item, and the answer is what the screen shows next. Locks in
order: the session (FOR UPDATE), its subject (FOR SHARE), then the unit."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.review_sessions import CurrentOut, DoneOut, current_out
from core_api.db.models import User
from core_api.db.session import DbSession
from core_api.domain.learning_day import learning_day
from core_api.domain.today import compose_today
from core_api.repositories.review import (
    ReviewSessionItemRepository,
    ReviewSessionRepository,
    session_counts,
)
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.today import TodayRepository
from core_api.repositories.unit import KnowledgeUnitRepository

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])


class SkipIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_session_id: uuid.UUID | None = None


class SkipOut(BaseModel):
    session_id: uuid.UUID | None
    next: CurrentOut | DoneOut | None


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _visible_unit(session: DbSession, user_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
    """The unit's subject id; 404 when the unit is not this user's or its subject was deleted,
    the same answer for both."""
    unit = KnowledgeUnitRepository(session, user_id).get(unit_id)
    if unit is None or SubjectRepository(session, user_id).get(unit.subject_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "unit_not_found")
    return unit.subject_id


@router.post("/units/{unit_id}/skip")
def skip_unit(
    unit_id: uuid.UUID, body: SkipIn, user: VerifiedUser, session: DbSession, now: Now
) -> SkipOut:
    subject_id = _visible_unit(session, user.id, unit_id)
    tz = ZoneInfo(user.timezone)
    day = learning_day(now, tz, user.day_start_hour)
    sessions = ReviewSessionRepository(session, user.id)
    held = None
    if body.review_session_id is not None:
        held = sessions.hold_for_update(body.review_session_id)
        if held is None:  # checked before anything is written
            raise _error(status.HTTP_404_NOT_FOUND, "session_not_found")
        if held.ended_at is not None or held.learning_day != day:
            held = None  # nothing open to give a replacement to: only the skip is kept
    units = KnowledgeUnitRepository(session, user.id)
    if held is None:
        units.skip(unit_id, now)
        return SkipOut(session_id=None, next=None)
    try:
        SubjectRepository(session, user.id).hold_for_share(subject_id)
    except SubjectNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "unit_not_found") from error
    items = ReviewSessionItemRepository(session, user.id)
    before = session_counts(items.progress(held.id))[1]
    if units.skip(unit_id, now):
        after = session_counts(items.progress(held.id))[1]
        missing = max(0, before - after)
        if missing:
            _replace(session, user, held.subject_id, held.id, missing, now)
    steps = items.progress(held.id)
    return SkipOut(session_id=held.id, next=current_out(False, steps, user.id, session, now))


def _replace(
    session: DbSession,
    user: User,
    subject_id: uuid.UUID | None,
    review_session_id: uuid.UUID,
    missing: int,
    now: datetime,
) -> None:
    items = ReviewSessionItemRepository(session, user.id)
    inside = frozenset(i.question_id for i in items.of_session(review_session_id))
    listed = SubjectRepository(session, user.id).list_with_exams()
    exams = {subject.id: exam.exam_date for subject, exam, _ in listed}
    reads = TodayRepository(session, user.id)
    due = [u for u in reads.scheduled_units() if subject_id in (None, u.subject_id)]
    fresh = [q for q in reads.new_questions() if subject_id in (None, q.subject_id)]
    plan = compose_today(
        due,
        fresh,
        exams,
        now=now,
        tz=ZoneInfo(user.timezone),
        day_start_hour=user.day_start_hour,
        unasked={s: n for s, n in reads.unasked_by_subject().items() if subject_id in (None, s)},
        exclude=inside,
        room=missing,
    )
    if plan.items:
        items.append(review_session_id, [item.question_id for item in plan.items])


@router.delete("/units/{unit_id}/skip", status_code=status.HTTP_204_NO_CONTENT)
def unskip_unit(
    unit_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    review_session_id: uuid.UUID | None = None,
) -> Response:
    """Undo a skip; 204 whether or not the unit was skipped. Nothing is added to or taken from an
    open session here: a question hidden by the skip is asked again, and the session cap (20)
    hides the last replacement, if any (`progress`)."""
    _visible_unit(session, user.id, unit_id)
    if review_session_id is not None:  # the same lock order as the skip
        if ReviewSessionRepository(session, user.id).hold_for_update(review_session_id) is None:
            raise _error(status.HTTP_404_NOT_FOUND, "session_not_found")
    KnowledgeUnitRepository(session, user.id).unskip(unit_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
