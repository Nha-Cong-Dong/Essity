"""Compose "what to study next" (T7.10b, US-15) from the ledger, the outlines and the exams, by
the pure rules in `domain.suggest`. Computed fresh on every call: no stored schedule, no AI."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from core_api.db.models import User
from core_api.domain.study_ledger import last_studied_days, ledger_day
from core_api.domain.suggest import (
    EmptyReason,
    SubjectInput,
    SuggestFilter,
    Suggestion,
    eligible_subjects,
    empty_state,
    suggest_finished,
    suggest_for_subject,
    suggest_today,
)
from core_api.repositories.stats import StatsRepository
from core_api.repositories.study_ledger import StudyLedgerRepository


class UnknownSubjectError(LookupError):
    pass


@dataclass(frozen=True)
class Suggestions:
    today: date
    suggestions: list[Suggestion]
    finished: list[Suggestion]
    empty: EmptyReason | None
    subject_names: dict[uuid.UUID, str]


def _inputs(session: Session, user: User) -> tuple[list[SubjectInput], dict[uuid.UUID, str]]:
    infos = StatsRepository(session, user.id).subjects()
    ledger = StudyLedgerRepository(session, user.id)
    last = last_studied_days(ledger.entries())
    leaves = ledger.leaves()
    inputs = [SubjectInput(i.id, i.exam_date, last.get(i.id), leaves.get(i.id, [])) for i in infos]
    return inputs, {i.id: i.name for i in infos}


def build_suggestions(
    session: Session, user: User, now: datetime, filters: SuggestFilter | None = None
) -> Suggestions:
    """`filters` is the hook for "this week only subject A" (T9.2); None filters nothing."""
    today = ledger_day(now, ZoneInfo(user.timezone), user.day_start_hour)
    inputs, names = _inputs(session, user)
    suggestions = suggest_today(inputs, today, filters)
    finished = suggest_finished(inputs, today, filters)
    empty = (
        None
        if suggestions
        else empty_state(len(inputs), eligible_subjects(inputs, today, filters), finished)
    )
    return Suggestions(today, suggestions, finished, empty, names)


def suggest_one(
    session: Session, user: User, now: datetime, subject_id: uuid.UUID
) -> tuple[date, Suggestion, str]:
    """The "Gợi ý cho hôm nay" button: one subject, same rules, no ranking."""
    today = ledger_day(now, ZoneInfo(user.timezone), user.day_start_hour)
    inputs, names = _inputs(session, user)
    subject = next((s for s in inputs if s.id == subject_id), None)
    if subject is None:
        raise UnknownSubjectError(subject_id)
    return today, suggest_for_subject(subject, today), names[subject_id]
