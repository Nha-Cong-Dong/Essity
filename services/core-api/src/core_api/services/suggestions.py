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
from core_api.repositories.study_filter import StudyFilterRepository
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


def subject_inputs(session: Session, user: User) -> tuple[list[SubjectInput], dict[uuid.UUID, str]]:
    infos = StatsRepository(session, user.id).subjects()
    ledger = StudyLedgerRepository(session, user.id)
    last = last_studied_days(ledger.entries())
    leaves = ledger.leaves()
    inputs = [SubjectInput(i.id, i.exam_date, last.get(i.id), leaves.get(i.id, [])) for i in infos]
    return inputs, {i.id: i.name for i in infos}


def learning_today(user: User, now: datetime) -> date:
    return ledger_day(now, ZoneInfo(user.timezone), user.day_start_hour)


def command_filters(
    session: Session, user: User, today: date, live: set[uuid.UUID]
) -> SuggestFilter | None:
    """The filters of "only subject A until D" and "subject B after D" that still hold on `today`
    (US-15 AC9: they end with the period). They are applied before the ranking, so a hidden
    subject never takes a place from one that is shown."""
    only: set[uuid.UUID] = set()
    hidden: dict[uuid.UUID, date] = {}
    for subject_id, mode, until in StudyFilterRepository(session, user.id).active():
        if subject_id not in live:  # a deleted subject's filter must not hide the others
            continue
        if mode == "only" and today <= until:
            only.add(subject_id)
        elif mode == "defer" and today < until:
            hidden[subject_id] = until
    if not only and not hidden:
        return None
    return SuggestFilter(only_subjects=only or None, hidden_until=hidden)


def build_suggestions(
    session: Session, user: User, now: datetime, filters: SuggestFilter | None = None
) -> Suggestions:
    """`filters` None: those a command put on the user's subjects (T9.2e); a value replaces them."""
    today = ledger_day(now, ZoneInfo(user.timezone), user.day_start_hour)
    inputs, names = subject_inputs(session, user)
    if filters is None:
        filters = command_filters(session, user, today, {i.id for i in inputs})
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
    inputs, names = subject_inputs(session, user)
    subject = next((s for s in inputs if s.id == subject_id), None)
    if subject is None:
        raise UnknownSubjectError(subject_id)
    return today, suggest_for_subject(subject, today), names[subject_id]
