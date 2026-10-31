"""`GET /v1/stats` (T9.4b, US-10): numbers per subject and the activity grid, for every subject
or one (`?subject_id=`). Reads only. No streak, no comparison with other people or periods."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.db.session import DbSession
from core_api.services.stats import UnknownSubjectError, build_stats

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])


class UnitWeightOut(BaseModel):
    unit: str  # page | slide | est_page: weights of different units are never summed
    studied: float
    total: float


class SyllabusOut(BaseModel):
    leaves: int
    studied_leaves: int
    percent: int | None
    by_unit: list[UnitWeightOut]


class TypeCountsOut(BaseModel):
    question_type: str
    ready: int
    practiced: int
    mastered: int


class SubjectStatsOut(BaseModel):
    id: uuid.UUID
    name: str
    exam_date: date | None
    days_left: int | None
    syllabus: SyllabusOut
    bank: list[TypeCountsOut]
    retention: float | None


class NamedOut(BaseModel):
    id: uuid.UUID
    name: str


class GridCellOut(BaseModel):
    day: date
    column: int
    row: int
    level: int
    future: bool
    exam_day: bool
    subjects: list[NamedOut]
    sections: list[NamedOut]
    cards_saved: int
    questions_answered: int


class StatsOut(BaseModel):
    today: date
    subjects: list[SubjectStatsOut]
    grid: list[GridCellOut]


@router.get("/stats")
def get_stats(
    user: VerifiedUser, session: DbSession, now: Now, subject_id: uuid.UUID | None = None
) -> StatsOut:
    try:
        stats = build_stats(session, user, now, subject_id)
    except UnknownSubjectError:
        raise HTTPException(status_code=404, detail="subject_not_found") from None
    return StatsOut(
        today=stats.today,
        subjects=[
            SubjectStatsOut(
                id=s.info.id,
                name=s.info.name,
                exam_date=s.info.exam_date,
                days_left=s.days_left,
                syllabus=SyllabusOut(
                    leaves=s.syllabus.leaves,
                    studied_leaves=s.syllabus.studied_leaves,
                    percent=s.syllabus.percent,
                    by_unit=[
                        UnitWeightOut(unit=u, studied=w.studied, total=w.total)
                        for u, w in s.syllabus.by_unit.items()
                    ],
                ),
                bank=[
                    TypeCountsOut(
                        question_type=kind,
                        ready=c.ready,
                        practiced=c.practiced,
                        mastered=c.mastered,
                    )
                    for kind, c in s.bank.items()
                ],
                retention=s.retention,
            )
            for s in stats.subjects
        ],
        grid=[
            GridCellOut(
                day=c.day,
                column=c.column,
                row=c.row,
                level=c.level,
                future=c.future,
                exam_day=c.exam_day,
                subjects=[NamedOut(id=i, name=stats.subject_names[i]) for i in c.subjects],
                sections=[NamedOut(id=i, name=stats.section_titles.get(i, "")) for i in c.sections],
                cards_saved=c.cards_saved,
                questions_answered=c.questions_answered,
            )
            for c in stats.grid
        ],
    )
