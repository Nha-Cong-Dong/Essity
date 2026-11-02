"""Repository of `practice_removal_log` (T9.2b, ADR-0029/0030): when a practice question was taken
out of practice or put back, added and never changed. The newest row of a question says whether it
is out; `practice_state.removed_at` is a cache of it (`PracticeStateRepository.rebuild` reads this
log). Every query filters on the user."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.db.models import PracticeRemovalLog


@dataclass(frozen=True)
class RemovalEvent:
    id: int
    question_id: uuid.UUID
    action: str
    at: datetime
    command_id: uuid.UUID | None

    @property
    def removed(self) -> bool:
        return self.action == "removed"


def _event(row: PracticeRemovalLog) -> RemovalEvent:
    return RemovalEvent(row.id, row.question_id, row.action, row.at, row.command_id)


class PracticeRemovalRepository:
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        if not isinstance(user_id, uuid.UUID):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("user_id must be a UUID")
        self.session = session
        self.user_id = user_id

    def append(
        self,
        question_id: uuid.UUID,
        action: str,
        *,
        at: datetime | None = None,
        command_id: uuid.UUID | None = None,
    ) -> RemovalEvent:
        """Add one event. The caller holds the question's row lock first (the undo's revision
        check and this insert must not interleave with another writer of the same question)."""
        row = PracticeRemovalLog(
            user_id=self.user_id,
            question_id=question_id,
            action=action,
            command_id=command_id,
        )
        if at is not None:
            row.at = at
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return _event(row)

    def latest(
        self, question_ids: Sequence[uuid.UUID] | None = None
    ) -> dict[uuid.UUID, RemovalEvent]:
        """The newest event of each question (of these, or of all this user's that have one)."""
        newest = (
            select(PracticeRemovalLog.question_id, func.max(PracticeRemovalLog.id).label("id"))
            .where(PracticeRemovalLog.user_id == self.user_id)
            .group_by(PracticeRemovalLog.question_id)
        )
        if question_ids is not None:
            newest = newest.where(PracticeRemovalLog.question_id.in_(question_ids))
        ids = newest.subquery()
        rows = self.session.scalars(
            select(PracticeRemovalLog).where(
                PracticeRemovalLog.user_id == self.user_id, PracticeRemovalLog.id == ids.c.id
            )
        ).all()
        return {row.question_id: _event(row) for row in rows}

    def rev(self, question_id: uuid.UUID) -> int:
        """The revision of "in practice" an undo checks: the id of the newest event, 0 if none."""
        newest = self.session.scalar(
            select(func.max(PracticeRemovalLog.id)).where(
                PracticeRemovalLog.user_id == self.user_id,
                PracticeRemovalLog.question_id == question_id,
            )
        )
        return int(newest or 0)

    def in_practice(self, question_id: uuid.UUID) -> bool:
        event = self.latest([question_id]).get(question_id)
        return event is None or not event.removed
