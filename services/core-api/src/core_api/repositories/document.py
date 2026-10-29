"""Documents of a user (T4.5): every query scoped to them (ARCH §6.2)."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.db.models import Document, User
from core_api.domain.documents import raw_key
from core_api.repositories.base import UserScopedRepository
from core_api.repositories.subject import SubjectRepository


class DocumentRejectedError(ValueError):
    """This file was stored once and was not the PDF declared: the same SHA-256 is the same
    bytes, so it would be refused again."""


class SizeMismatchError(ValueError):
    """The file is being uploaded with another size: the URL already signed fixes the size."""


class QuotaExceededError(ValueError):
    """The account's files, uploaded or on their way, would go over its quota."""


class StorageFullError(ValueError):
    """Everyone's files would go over the store's cap."""


def stored_bytes_of_everyone(session: Session) -> int:
    """Bytes of every document row, any user: the one query here that is not scoped to a user,
    for the store-wide cap (plan P17). It reads a sum, never a row.

    The cap is approximate: each user's asks are serialized, not everyone's, so N users asking
    at once can go over it by up to N files. Accepted (P17): it bounds cost, not a promise."""
    return session.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0))) or 0


class DocumentRepository(UserScopedRepository[Document]):
    model = Document

    def lock(self, id: uuid.UUID) -> Document | None:
        """This user's document, held FOR UPDATE until commit and read afresh: one confirm at a
        time, and none while cleanup deletes it (plan R2)."""
        return self.session.scalars(
            self._select()
            .where(Document.id == id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()

    def of_subject(self, subject_id: uuid.UUID) -> list[Document]:
        """This user's documents of one subject, oldest first (id breaks ties)."""
        return list(
            self.session.scalars(
                self._select()
                .where(Document.subject_id == subject_id)
                .order_by(Document.created_at, Document.id)
            )
        )

    def indexed_of_subject(self, subject_id: uuid.UUID, limit: int) -> list[Document]:
        """This user's indexed documents of one subject, newest first (id breaks ties)."""
        return list(
            self.session.scalars(
                self._select()
                .where(Document.subject_id == subject_id, Document.status == "indexed")
                .order_by(Document.created_at.desc(), Document.id)
                .limit(limit)
            )
        )

    def reserve(
        self,
        subject_id: uuid.UUID,
        *,
        sha256: str,
        size_bytes: int,
        short_name: str,
        now: datetime,
        quota_bytes: int,
        global_quota_bytes: int,
    ) -> tuple[Document, bool]:
        """The row to sign an upload URL for, and whether it is new.

        Locks, in this order (plan P8): the user row FOR NO KEY UPDATE, so one user's
        reservations go one at a time and the quota sum holds (a login's KEY SHARE still
        passes); the subject FOR SHARE (`hold_for_share`), so no file lands on a subject being
        deleted; then the file's row, if the subject has it.

        The same file again: uploaded → that row, untouched; pending → that row, `presigned_at`
        moved to `now` so cleanup waits for the new URL (plan R2), or SizeMismatchError for
        another size; rejected → DocumentRejectedError. A new file must fit the account's
        quota (QuotaExceededError) and the store's cap (StorageFullError). SubjectNotFoundError
        for a subject the user cannot see.
        """
        self.session.execute(
            select(User.id).where(User.id == self.user_id).with_for_update(key_share=True)
        )
        SubjectRepository(self.session, self.user_id).hold_for_share(subject_id)
        existing = self.session.scalars(
            self._select()
            .where(Document.subject_id == subject_id, Document.sha256 == sha256)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        if existing is not None:
            if existing.status == "rejected":
                raise DocumentRejectedError
            if existing.status == "pending":
                if existing.size_bytes != size_bytes:
                    raise SizeMismatchError
                existing.presigned_at = now
                self.session.flush()
            return existing, False

        used = self.session.scalar(
            self._select().with_only_columns(func.coalesce(func.sum(Document.size_bytes), 0))
        )
        if (used or 0) + size_bytes > quota_bytes:
            raise QuotaExceededError
        if stored_bytes_of_everyone(self.session) + size_bytes > global_quota_bytes:
            raise StorageFullError
        document = self.add(
            Document(
                subject_id=subject_id,
                short_name=short_name,
                sha256=sha256,
                size_bytes=size_bytes,
                object_key=raw_key(self.user_id, subject_id, sha256),
                status="pending",
                presigned_at=now,
            )
        )
        self.session.flush()
        return document, True
