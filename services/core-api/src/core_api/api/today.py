"""`GET /v1/today` (T2.8, T7.11, US-03, ARCH §5.3): today's session, composed by `compose_today`
from what `TodayRepository` reads, with the v2 parts around it (what to study next, the review
with a reason for each question, the unfinished work). Starting the session is
`POST /v1/review-sessions`; the only writes here are the lazy review-question jobs (T7.9).

The backlog note comes back structured (subject, sessions, days, units): the screen words it, so
the sentence stays copy the user approves (T2.8 plan C5).

Contract for T8.5: fields are only ever added. `practice` is null until T8.5 fills it.
`?subject_id=` is "Ôn riêng môn này": it narrows `review`, `session` and `backlog` the way
`POST /v1/review-sessions {"subject_id"}` narrows the session it starts (same inputs, so the
same questions); `next_study` and `unfinished` never depend on it."""

import uuid
from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.review_sessions import ReasonOut
from core_api.api.suggestions import SuggestionOut, suggestion_out
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
from core_api.services.today import build_v2, enqueue_lazy_questions

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
    units: int


class InProgressOut(BaseModel):
    session_id: uuid.UUID
    position: int
    total: int


class TodaySubject(BaseModel):
    id: uuid.UUID
    name: str
    exam_date: date
    days_until_exam: int


class UnfinishedOut(BaseModel):
    session_id: uuid.UUID
    subject_id: uuid.UUID
    line: str


class NextStudyOut(BaseModel):
    items: list[SuggestionOut]
    empty_reason: str | None  # set exactly when `items` is empty
    links: list[Literal["review", "practice", "subjects"]]


class ReviewItemOut(BaseModel):
    question_id: uuid.UUID
    subject_id: uuid.UUID
    why: str
    reason: ReasonOut


class ReviewOut(BaseModel):
    items: list[ReviewItemOut]
    minutes: int
    next_due_day: date | None  # only when nothing is due today
    new_saved_today: bool  # a card saved today waits for the next learning day


class TodayOut(BaseModel):
    learning_day: date
    state: TodayState
    session: SessionOut | None
    in_progress: InProgressOut | None
    backlog: BacklogOut | None
    next_day: date | None
    subjects: list[TodaySubject]
    unfinished: list[UnfinishedOut]
    next_study: NextStudyOut
    review: ReviewOut
    practice: None = None  # T8.5 adds the practice part here and changes nothing above


@router.get("/today")
def get_today(
    user: VerifiedUser, session: DbSession, now: Now, subject_id: uuid.UUID | None = None
) -> TodayOut:
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
    if subject_id is not None and subject_id not in exams:  # as the session start: 404
        raise HTTPException(status.HTTP_404_NOT_FOUND, "subject_not_found")
    reads = TodayRepository(session, user.id)
    # The same three filters as `POST /v1/review-sessions`, before composing.
    units = [u for u in reads.scheduled_units() if subject_id in (None, u.subject_id)]
    fresh = [q for q in reads.new_questions(day=day) if subject_id in (None, q.subject_id)]
    plan = compose_today(
        units,
        fresh,
        exams,
        now=now,
        tz=tz,
        day_start_hour=user.day_start_hour,
        unasked={
            s: n for s, n in reads.unasked_by_subject(day=day).items() if subject_id in (None, s)
        },
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
            units=plan.backlog.units,
        )
    parts = build_v2(session, user, now, plan, units, reads)
    enqueue_lazy_questions(session, user, now, reads, [i.question_id for i in plan.items])
    return TodayOut(
        learning_day=day,
        state=state,
        session=session_out,
        in_progress=in_progress,
        backlog=backlog,
        next_day=plan.next_day,
        subjects=subjects,
        unfinished=[
            UnfinishedOut(session_id=u.session_id, subject_id=u.subject_id, line=u.line)
            for u in parts.unfinished
        ],
        next_study=NextStudyOut(
            items=[suggestion_out(i.suggestion, i.subject_name) for i in parts.next_study.items],
            empty_reason=parts.next_study.empty_reason,
            links=list(parts.next_study.links),
        ),
        review=ReviewOut(
            items=[
                ReviewItemOut(
                    question_id=i.question_id,
                    subject_id=i.subject_id,
                    why=i.why,
                    reason=ReasonOut(
                        kind=i.kind,
                        retrievability=i.retrievability,
                        days_since_last=i.days_since_last,
                    ),
                )
                for i in parts.review.items
                if i.question_id is not None
            ],
            minutes=parts.review.minutes,
            next_due_day=parts.review.next_due_day,
            new_saved_today=parts.review.new_saved_today,
        ),
    )
