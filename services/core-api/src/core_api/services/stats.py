"""Compose the statistics of a user (T9.4b, US-10): one entry per visible subject and the
activity grid, from `StatsRepository` and the pure rules in `domain.stats`. No streak, no
comparison."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from core_api.db.models import User
from core_api.domain.learning_day import learning_day
from core_api.domain.stats import (
    GridCell,
    SubjectSpan,
    SyllabusProgress,
    TypeCounts,
    activity_grid,
    days_left,
    question_bank,
    retention,
    syllabus_progress,
)
from core_api.repositories.stats import StatsRepository, SubjectInfo


class UnknownSubjectError(LookupError):
    pass


@dataclass(frozen=True)
class SubjectStats:
    info: SubjectInfo
    days_left: int | None
    syllabus: SyllabusProgress
    bank: dict[str, TypeCounts]
    retention: float | None


@dataclass(frozen=True)
class Stats:
    today: date
    subjects: list[SubjectStats]
    grid: list[GridCell]
    subject_names: dict[uuid.UUID, str]
    section_titles: dict[uuid.UUID, str]


def build_stats(
    session: Session, user: User, now: datetime, subject_id: uuid.UUID | None = None
) -> Stats:
    tz = ZoneInfo(user.timezone)
    today = learning_day(now, tz, user.day_start_hour)
    repo = StatsRepository(session, user.id)
    infos = repo.subjects()
    if subject_id is not None:
        infos = [i for i in infos if i.id == subject_id]
        if not infos:
            raise UnknownSubjectError(subject_id)
    leaves, banks, recalls = repo.leaves(), repo.bank(now), repo.retentions(now)
    subjects = [
        SubjectStats(
            info=i,
            days_left=days_left(i.exam_date, today),
            syllabus=syllabus_progress(leaves.get(i.id, [])),
            bank=question_bank(banks.get(i.id, [])),
            retention=retention(recalls.get(i.id, [])),
        )
        for i in infos
    ]
    grid = activity_grid(
        [SubjectSpan(i.id, i.created_at, i.exam_date) for i in infos],
        repo.events(),
        today,
        tz,
        user.day_start_hour,
    )
    return Stats(
        today=today,
        subjects=subjects,
        grid=grid,
        subject_names={i.id: i.name for i in infos},
        section_titles=repo.section_titles(),
    )
