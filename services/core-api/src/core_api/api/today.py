"""`GET /v1/today` (T2.8, T7.11, US-03, ARCH §5.3): today's session, composed by `compose_today`
from what `TodayRepository` reads, with the v2 parts around it (what to study next, the review
with a reason for each question, the unfinished work). Starting the session is
`POST /v1/review-sessions`; the only writes here are the lazy review-question jobs (T7.9).

The backlog note comes back structured (subject, sessions, days, units): the screen words it, so
the sentence stays copy the user approves (T2.8 plan C5).

Contract (T8.5): fields are only ever added. `review` holds the cards and the practice questions
due together (`item_kind`, one cap); `practice` has one line per subject with ready questions never
attempted, null when there are none (a due question is in `review` only, US-06 AC8).
`?subject_id=` is "Ôn riêng môn này": it narrows `review`, `session`, `practice`, `backlog` the way
`POST /v1/review-sessions {"subject_id"}` narrows the session it starts (same inputs, so the
same questions); `next_study` and `unfinished` never depend on it."""

import uuid
from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.review_sessions import ReasonOut
from core_api.api.suggestions import SuggestionOut, suggestion_out
from core_api.db.models.question import Question
from core_api.db.session import DbSession
from core_api.domain.learning_day import learning_day
from core_api.domain.subjects import days_until_exam
from core_api.domain.today_v2 import ReviewItem
from core_api.repositories.review import ReviewSessionRepository, session_counts
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.today import PracticeCandidate, TodayRepository
from core_api.services.today import (
    MixedEntry,
    build_v2,
    compose_mixed,
    enqueue_lazy_questions,
    session_steps,
)

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
    item_kind: Literal["card", "practice"] = "card"  # T8.5: a practice question is not a card
    front: str | None = None  # the question text, for the subject screen's card stack
    back: str | None = None  # its reference answer (the flip side)


class ReviewOut(BaseModel):
    items: list[ReviewItemOut]
    minutes: int
    next_due_day: date | None  # only when nothing is due today
    new_saved_today: bool  # a card saved today waits for the next learning day


class PracticeLineOut(BaseModel):
    subject_id: uuid.UUID
    subject_name: str
    ready_questions: int  # ready and never attempted
    question_types: int


class PracticePartOut(BaseModel):
    lines: list[PracticeLineOut]


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
    practice: PracticePartOut | None = None  # T8.5; None when nothing is ready and new


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
    mixed = compose_mixed(session, user, now, reads, subject_id=subject_id)
    plan, units = mixed.plan, mixed.units

    in_progress = None
    open_session = ReviewSessionRepository(session, user.id).open_on(day)
    if open_session is not None:
        steps = session_steps(session, user.id, open_session.id)
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
    elif mixed.entries:
        state = "ready"
    elif not reads.has_questions() and not mixed.fresh and not reads.has_practice():
        state = "no_questions"
    elif all(exam_day < day for exam_day in exams.values()):
        state = "all_exams_over"
    else:
        state = "rested"

    session_out = None
    if mixed.entries:
        in_session = list(dict.fromkeys(item.subject_id for item in mixed.entries))
        session_out = SessionOut(
            question_count=len(mixed.entries),
            minutes=mixed.minutes,
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
    enqueue_lazy_questions(
        session, user, now, reads, [i.question_id for i in plan.items]
    )  # cards only
    return TodayOut(
        learning_day=day,
        state=state,
        session=session_out,
        in_progress=in_progress,
        backlog=backlog,
        next_day=mixed.next_day,
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
            items=_with_text(
                session,
                user.id,
                _review_items(mixed.entries, {i.question_id: i for i in parts.review.items}),
            ),
            minutes=mixed.minutes,
            next_due_day=None if mixed.entries else mixed.next_day,
            new_saved_today=parts.review.new_saved_today,
        ),
        practice=_practice_part(mixed.fresh, names),
    )


def _with_text(
    session: DbSession, user_id: uuid.UUID, items: list[ReviewItemOut]
) -> list[ReviewItemOut]:
    """Front and back of each item's question, read in one query."""
    if not items:
        return items
    rows = session.execute(
        select(Question.id, Question.prompt, Question.reference_answer).where(
            Question.user_id == user_id, Question.id.in_([i.question_id for i in items])
        )
    ).all()
    text = {row.id: (row.prompt, row.reference_answer) for row in rows}
    return [
        item.model_copy(
            update={
                "front": text.get(item.question_id, (None, None))[0],
                "back": text.get(item.question_id, (None, None))[1],
            }
        )
        for item in items
    ]


def _practice_why(entry: MixedEntry) -> str:
    return (
        f"Câu luyện tập đến hạn; khả năng nhớ khoảng {round((entry.retrievability or 0) * 100)}%."
    )


def _review_items(
    entries: list[MixedEntry], cards: dict[uuid.UUID | None, ReviewItem]
) -> list[ReviewItemOut]:
    out: list[ReviewItemOut] = []
    for entry in entries:
        if entry.kind == "practice":
            out.append(
                ReviewItemOut(
                    question_id=entry.question_id,
                    subject_id=entry.subject_id,
                    why=_practice_why(entry),
                    reason=ReasonOut(
                        kind="review",
                        retrievability=entry.retrievability,
                        days_since_last=entry.days_since_last,
                    ),
                    item_kind="practice",
                )
            )
            continue
        card = cards[entry.question_id]
        out.append(
            ReviewItemOut(
                question_id=entry.question_id,
                subject_id=card.subject_id,
                why=card.why,
                reason=ReasonOut(
                    kind=card.kind,
                    retrievability=card.retrievability,
                    days_since_last=card.days_since_last,
                ),
            )
        )
    return out


def _practice_part(
    fresh: list[PracticeCandidate], names: dict[uuid.UUID, str]
) -> PracticePartOut | None:
    by_subject: dict[uuid.UUID, list[PracticeCandidate]] = {}
    for candidate in fresh:
        by_subject.setdefault(candidate.subject_id, []).append(candidate)
    lines = [
        PracticeLineOut(
            subject_id=subject_id,
            subject_name=names.get(subject_id, ""),
            ready_questions=len(rows),
            question_types=len({c.type_id for c in rows}),
        )
        for subject_id, rows in sorted(
            by_subject.items(), key=lambda kv: (names.get(kv[0], ""), str(kv[0]))
        )
    ]
    return PracticePartOut(lines=lines) if lines else None
