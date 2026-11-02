"""Repository of `command_log` (T9.2b, ADR-0030): one row per applied command, found again by the
client's `command_id` (a retry) or as the newest open one of a screen session (an undo). Every
query filters on the user: the same `command_id` of another user is another row. The database
lets a row change once, applied to undone (`command_log_guard`)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import null, select, update
from sqlalchemy.dialects.postgresql import insert

from core_api.db.models import CommandLog
from core_api.repositories.base import UserScopedRepository


class CommandLogRepository(UserScopedRepository[CommandLog]):
    model = CommandLog

    def add_new(
        self,
        *,
        command_id: uuid.UUID,
        payload_hash: str,
        raw_text: str,
        ops: Any,
        inverse: Any,
        affected_count: int,
        screen_session_id: uuid.UUID | None = None,
        subject_id: uuid.UUID | None = None,
        undo_revs: Any | None = None,
        run_id: uuid.UUID | None = None,
    ) -> CommandLog | None:
        """Insert the command; None if this user already has a row for `command_id` (a retry
        that raced: the caller rolls back and reads the stored row)."""
        row = self.session.execute(
            insert(CommandLog)
            .values(
                id=uuid.uuid4(),
                user_id=self.user_id,
                command_id=command_id,
                payload_hash=payload_hash,
                raw_text=raw_text,
                ops_json=ops,
                inverse_json=inverse,
                affected_count=affected_count,
                screen_session_id=screen_session_id,
                subject_id=subject_id,
                undo_revs_json=null()
                if undo_revs is None
                else undo_revs,  # SQL NULL, not JSON null
                run_id=run_id,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "command_id"])
            .returning(CommandLog.id)
        ).first()
        if row is None:
            return None
        return self.get(row[0])

    def by_command_id(self, command_id: uuid.UUID) -> CommandLog | None:
        return self.session.scalars(
            self._select().where(CommandLog.command_id == command_id)
        ).one_or_none()

    def latest_open(self, screen_session_id: uuid.UUID) -> CommandLog | None:
        """The newest command of the session not yet undone: the only one an undo may reverse."""
        return self.session.scalars(
            self._select()
            .where(
                CommandLog.screen_session_id == screen_session_id, CommandLog.status == "applied"
            )
            .order_by(CommandLog.seq.desc())
            .limit(1)
        ).one_or_none()

    def lock(self, command_id: uuid.UUID) -> CommandLog | None:
        """This user's command, held FOR UPDATE until commit and read afresh."""
        return self.session.scalars(
            self._select()
            .where(CommandLog.command_id == command_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()

    def after(self, screen_session_id: uuid.UUID, seq: int) -> list[CommandLog]:
        """The commands of the session logged after `seq`, oldest first."""
        return list(
            self.session.scalars(
                self._select()
                .where(CommandLog.screen_session_id == screen_session_id, CommandLog.seq > seq)
                .order_by(CommandLog.seq)
            )
        )

    def mark_undone(
        self, command_id: uuid.UUID, *, undo_revs: Any | None = None, at: datetime | None = None
    ) -> CommandLog | None:
        """Flip applied to undone, once, under the row's lock; None if it is not there (or is not
        this user's), was already undone, or is not the newest applied command of its screen
        session (an undo takes the newest first; T9.2b review Y3)."""
        locked = self.session.scalars(
            self._select()
            .where(CommandLog.command_id == command_id, CommandLog.status == "applied")
            .with_for_update()
        ).one_or_none()
        if locked is None:
            return None
        if locked.screen_session_id is not None:
            newer = self.session.scalar(
                select(CommandLog.id)
                .where(
                    CommandLog.user_id == self.user_id,
                    CommandLog.screen_session_id == locked.screen_session_id,
                    CommandLog.status == "applied",
                    CommandLog.seq > locked.seq,
                )
                .limit(1)
            )
            if newer is not None:
                return None
        values: dict[str, Any] = {"status": "undone", "undone_at": at or datetime.now(UTC)}
        if undo_revs is not None and locked.undo_revs_json is None:
            values["undo_revs_json"] = undo_revs
        self.session.execute(
            update(CommandLog)
            .where(CommandLog.user_id == self.user_id, CommandLog.id == locked.id)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        self.session.refresh(locked)
        return locked

    def delete(self, id: uuid.UUID) -> bool:
        raise NotImplementedError("a command is kept: it is only undone")
