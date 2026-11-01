"""`GET /v1/today` (T2.8, US-03, ARCH §5.3): today's session, composed by `compose_today` from
what `TodayRepository` reads. Reads only; starting the session is `POST /v1/review-sessions`.

The backlog note comes back structured (subject, sessions, days): the screen words it, so the
sentence stays copy the user approves (T2.8 plan C5)."""

import uuid
from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.db.session import DbSession
from core_api.domain.learning_day import learning_day
from core_api.domain.subjects import days_until_exam
from core_api.domain.today import compose_today
from core_api.repositories.review import (
    ReviewSessionItemRepository,
    ReviewSessionRepository,
    session_counts,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.today import TodayRepository

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

TodayState = Literal[
    "ready", "in_progress", "rested", "no_questions", "no_subjects", "all_exams_over"
]


class SubjectRef(BaseModel):
    id: uuid.UUID
    name: str


class SessionOut(BaseModel):
    question_count: int
    minutes: int
    subjects: list[SubjectRef]


class BacklogOut(BaseModel):
    subject_id: uuid.UUID
    subject_name: str
    sessions: int
    days: int


class InProgressOut(BaseModel):
    session_id: uuid.UUID
    position: int
    total: int


class TodaySubject(BaseModel):
    id: uuid.UUID
    name: str
    exam_date: date
    days_until_exam: int


class TodayOut(BaseModel):
    learning_day: date
    state: TodayState
    session: SessionOut | None
    in_progress: InProgressOut | None
    backlog: BacklogOut | None
    next_day: date | None
    subjects: list[TodaySubject]


@router.get("/today")
def get_today(user: VerifiedUser, session: DbSession, now: Now) -> TodayOut:
    tz = ZoneInfo(user.timezone)
    day = learning_day(now, tz, user.day_start_hour)
    listed = SubjectRepository(session, user.id).list_with_exams()
    names = {subject.id: subject.name for subject, _, _ in listed}
    exams = {subject.id: exam.exam_date for subject, exam, _ in listed}
    subjects = [
        TodaySubject(
            id=subject.id,
            name=subject.name,
            exam_date=exam.exam_date,
            days_until_exam=days_until_exam(exam.exam_date, now, tz, user.day_start_hour),
        )
        for subject, exam, _ in listed
    ]
    reads = TodayRepository(session, user.id)
    plan = compose_today(
        reads.scheduled_units(),
        reads.new_questions(day=day),
        exams,
        now=now,
        tz=tz,
        day_start_hour=user.day_start_hour,
        unasked=reads.unasked_by_subject(day=day),
    )

    in_progress = None
    open_session = ReviewSessionRepository(session, user.id).open_on(day)
    if open_session is not None:
        steps = ReviewSessionItemRepository(session, user.id).progress(open_session.id)
        answered, total = session_counts(steps)
        if answered < total:
            in_progress = InProgressOut(
                session_id=open_session.id, position=answered + 1, total=total
            )

    state: TodayState
    if in_progress is not None:
        state = "in_progress"
    elif not listed:
        state = "no_subjects"
    elif plan.items:
        state = "ready"
    elif not reads.has_questions():
        state = "no_questions"
    elif all(exam_day < day for exam_day in exams.values()):
        state = "all_exams_over"
    else:
        state = "rested"

    session_out = None
    if plan.items:
        in_session = list(dict.fromkeys(item.subject_id for item in plan.items))
        session_out = SessionOut(
            question_count=len(plan.items),
            minutes=plan.minutes,
            subjects=[SubjectRef(id=s, name=names[s]) for s in in_session],
        )
    backlog = None
    if plan.backlog is not None:
        backlog = BacklogOut(
            subject_id=plan.backlog.subject_id,
            subject_name=names[plan.backlog.subject_id],
            sessions=plan.backlog.sessions,
            days=plan.backlog.days,
        )
    return TodayOut(
        learning_day=day,
        state=state,
        session=session_out,
        in_progress=in_progress,
        backlog=backlog,
        next_day=plan.next_day,
        subjects=subjects,
    )
