"""Repository of `study_filter` (T9.2b, ADR-0030): the suggestion filter a command put on a
subject. A row stays for good: clearing sets `mode` to NULL and raises `rev` (no DELETE, so `rev`
never returns to a value an undo has already seen). Every query filters on the user."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core_api.db.models import StudyFilter


@dataclass(frozen=True)
class FilterState:
    mode: str | None
    until: date | None
    rev: int  # 0: no row yet


NO_FILTER = FilterState(None, None, 0)


class StudyFilterRepository:
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        if not isinstance(user_id, uuid.UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("user_id must be a UUID")
        self.session = session
        self.user_id = user_id

    def _row(self, subject_id: uuid.UUID, *, lock: bool = False) -> StudyFilter | None:
        query = select(StudyFilter).where(
            StudyFilter.user_id == self.user_id, StudyFilter.subject_id == subject_id
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalars(query).one_or_none()

    @staticmethod
    def _state(row: StudyFilter | None) -> FilterState:
        return NO_FILTER if row is None else FilterState(row.mode, row.until, row.rev)

    def lock(self, subject_id: uuid.UUID) -> FilterState:
        """Take the filter's lock and read it. With a row: FOR UPDATE. Without one there is
        nothing to lock, so a transaction advisory lock on (user, subject) stands for it (the
        plan's lock order: command_log, doc_section, question, study_filter, unit)."""
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"study_filter:{self.user_id}:{subject_id}"},
        )
        return self._state(self._row(subject_id, lock=True))

    def get(self, subject_id: uuid.UUID) -> FilterState:
        return self._state(self._row(subject_id))

    def set(self, subject_id: uuid.UUID, mode: str, until: date) -> FilterState:
        """Put a filter on the subject; the revision goes up by one (1 for a new row)."""
        return self._write(subject_id, mode, until)

    def clear(self, subject_id: uuid.UUID) -> FilterState:
        """No filter on the subject: `mode` and `until` empty, the row and a higher `rev` stay."""
        return self._write(subject_id, None, None)

    def _write(self, subject_id: uuid.UUID, mode: str | None, until: date | None) -> FilterState:
        row = self._row(subject_id, lock=True)
        if row is None:
            row = StudyFilter(user_id=self.user_id, subject_id=subject_id, rev=1)
            self.session.add(row)
        else:
            row.rev += 1
        row.mode = mode
        row.until = until
        self.session.flush()
        return self._state(row)
