"""Note files on their way to a session (T4.13b): every query scoped to the user (ARCH §6.2)."""

import uuid
from datetime import datetime

from sqlalchemy import func, select

from core_api.db.models import NoteFile, NoteUpload, User
from core_api.domain.study_session import note_key
from core_api.repositories.base import UserScopedRepository

MAX_NOTES = 20


class BadNoteError(ValueError):
    """The same file (SHA-256) was asked for with another type or size."""


class TooManyNotesError(ValueError):
    """The session already has the most notes it may have."""


class NoteQuotaExceededError(ValueError):
    """The account's notes, confirmed or on their way, would go over its quota."""


class NoteUploadRepository(UserScopedRepository[NoteUpload]):
    model = NoteUpload

    def reserve(
        self,
        session_id: uuid.UUID,
        *,
        sha256: str,
        mime: str,
        size_bytes: int,
        now: datetime,
        quota_bytes: int,
    ) -> tuple[NoteUpload, bool]:
        """The row to sign a URL for, and whether it is new.

        The user row is locked FOR NO KEY UPDATE first, so one account's reservations go one at a
        time and the quota sum holds (as `DocumentRepository.reserve`). The same file again moves
        `presigned_at` to `now` (BadNoteError for another type or size). A new one must keep the
        session at `MAX_NOTES` (TooManyNotesError) and the account under its quota
        (NoteQuotaExceededError); files confirmed and on their way both count.
        """
        self.session.execute(
            select(User.id).where(User.id == self.user_id).with_for_update(key_share=True)
        )
        existing = self.session.scalars(
            self._select()
            .where(NoteUpload.session_id == session_id, NoteUpload.sha256 == sha256)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        if existing is not None:
            if (existing.mime, existing.size_bytes) != (mime, size_bytes):
                raise BadNoteError
            existing.presigned_at = now
            self.session.flush()
            return existing, False

        on_the_way = self.session.scalar(
            select(func.count()).where(
                NoteUpload.user_id == self.user_id, NoteUpload.session_id == session_id
            )
        )
        if (on_the_way or 0) >= MAX_NOTES:
            raise TooManyNotesError
        pending = self.session.scalar(
            select(func.coalesce(func.sum(NoteUpload.size_bytes), 0)).where(
                NoteUpload.user_id == self.user_id
            )
        )
        stored = self.session.scalar(
            select(func.coalesce(func.sum(NoteFile.size_bytes), 0)).where(
                NoteFile.user_id == self.user_id
            )
        )
        used = (pending or 0) + (stored or 0)
        if used + size_bytes > quota_bytes:
            raise NoteQuotaExceededError
        upload = self.add(
            NoteUpload(
                session_id=session_id,
                object_key=note_key(self.user_id, session_id, sha256, mime),
                sha256=sha256,
                mime=mime,
                size_bytes=size_bytes,
                presigned_at=now,
            )
        )
        self.session.flush()
        return upload, True

    def lock_of_session(self, session_id: uuid.UUID, sha256s: list[str]) -> list[NoteUpload]:
        """This session's pending rows for these files, held FOR UPDATE until commit: cleanup
        skips them while a confirm decides about them."""
        if not sha256s:
            return []
        return list(
            self.session.scalars(
                self._select()
                .where(NoteUpload.session_id == session_id, NoteUpload.sha256.in_(sha256s))
                .with_for_update()
            )
        )
