"""Repository of `study_filter` (T9.2b, ADR-0030): the suggestion filter a command put on a
subject. A row stays for good: clearing sets `mode` to NULL and raises `rev` (no DELETE, so `rev`
never returns to a value an undo has already seen). Every query filters on the user."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, text

from core_api.db.models import StudyFilter
from core_api.repositories.base import UserScopedRepository


@dataclass(frozen=True)
class FilterState:
    mode: str | None
    until: date | None
    rev: int  # 0: no row yet


NO_FILTER = FilterState(None, None, 0)


class StudyFilterRepository(UserScopedRepository[StudyFilter]):  # pyright: ignore[reportInvalidTypeArguments]
    """Scoped like every repository (the structural rule). The key is (user, subject), not an
    `id`, so the inherited by-id methods do not apply: `state(subject_id)` is the read."""

    model = StudyFilter  # pyright: ignore[reportAssignmentType]

    def get(self, id: uuid.UUID) -> StudyFilter | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        raise NotImplementedError("a filter is read by subject: use `state`")

    def delete(self, id: uuid.UUID) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        raise NotImplementedError("a filter is cleared, never deleted (ABA): use `clear`")

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

    def state(self, subject_id: uuid.UUID) -> FilterState:
        return self._state(self._row(subject_id))

    def set(self, subject_id: uuid.UUID, mode: str | None, until: date | None) -> FilterState:
        """Put a filter on the subject; the revision goes up by one (1 for a new row). The lock
        is taken here (a no-op when the caller holds it): two writers of a new row must not race.
        `mode` and `until` are both set or both empty (T9.2b review Y1): the check is here, not in
        the database."""
        self.lock(subject_id)
        return self._write(subject_id, mode, until)

    def clear(self, subject_id: uuid.UUID) -> FilterState:
        """No filter on the subject: `mode` and `until` empty, the row and a higher `rev` stay."""
        self.lock(subject_id)
        return self._write(subject_id, None, None)

    def _write(self, subject_id: uuid.UUID, mode: str | None, until: date | None) -> FilterState:
        if (mode is None) != (until is None):
            raise ValueError("a filter has a mode and an end date, or neither")
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
