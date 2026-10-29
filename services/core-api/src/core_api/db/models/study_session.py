import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, not_blank, one_of

SESSION_STATUSES = frozenset({"draft", "confirmed"})
# How the first extraction ended: a card to confirm (proposed), a question back (clarify), notes
# only (note_only), or no card (failed / disabled / quota / no_documents): the manual form.
EXTRACTIONS = frozenset(
    {"proposed", "note_only", "clarify", "failed", "disabled", "quota", "no_documents"}
)
DEPTHS = frozenset({"deep", "skim", "unclear"})
NOTE_MIMES = frozenset(
    {"image/jpeg", "image/png", "application/pdf", "text/plain", "text/markdown"}
)
DESCRIPTION_MAX = 2000


class StudySession(UserOwned, Base):
    """One study session the learner logged (US-02, T4.12).

    `description_raw` is layer 1 (ADR-0008): saved before extraction runs, never changed by AI.
    A draft is a description whose card is not confirmed yet; confirming it fills `studied_on`
    (the real study day, Q14), `learning_day` (the day it was logged) and `confirmed_at`.
    """

    __tablename__ = "study_session"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subject_id", "user_id"], ["subject.id", "subject.user_id"], ondelete="CASCADE"
        ),
        UniqueConstraint("id", "user_id"),
        Index(None, "subject_id", "status"),
        CheckConstraint(not_blank("description_raw"), name="description_not_blank"),
        CheckConstraint(
            f"char_length(description_raw) <= {DESCRIPTION_MAX}", name="description_max"
        ),
        CheckConstraint(one_of("status", SESSION_STATUSES), name="status_known"),
        CheckConstraint(one_of("extraction", EXTRACTIONS), name="extraction_known"),
        CheckConstraint(
            "(status = 'confirmed') = (confirmed_at IS NOT NULL)", name="confirmed_iff_stamped"
        ),
        CheckConstraint(
            "status = 'draft' OR (studied_on IS NOT NULL AND learning_day IS NOT NULL)",
            name="confirmed_has_dates",
        ),
        CheckConstraint(
            "studied_on IS NULL OR studied_on <= learning_day", name="studied_not_after_logged"
        ),
    )

    subject_id: Mapped[uuid.UUID]
    description_raw: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft")
    extraction: Mapped[str] = mapped_column(String(14))
    studied_on: Mapped[date | None] = mapped_column(Date)
    learning_day: Mapped[date | None] = mapped_column(Date)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionRange(UserOwned, Base):
    """A page range of one document the session covered (file pages, 1-based; labels as printed)."""

    __tablename__ = "session_range"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_session.id", "study_session.user_id"],
            ondelete="CASCADE",
        ),
        # No cascade: a document with confirmed sessions is not dropped silently.
        ForeignKeyConstraint(["document_id", "user_id"], ["document.id", "document.user_id"]),
        UniqueConstraint("session_id", "position"),
        Index(None, "document_id"),
        CheckConstraint("start_page >= 1 AND start_page <= end_page", name="pages_ordered"),
        CheckConstraint(one_of("depth", DEPTHS), name="depth_known"),
        CheckConstraint("position >= 0", name="position_from_zero"),
    )

    session_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    start_page: Mapped[int] = mapped_column(Integer)
    end_page: Mapped[int] = mapped_column(Integer)
    start_label: Mapped[str | None] = mapped_column(String(40))
    end_label: Mapped[str | None] = mapped_column(String(40))
    depth: Mapped[str] = mapped_column(String(7))
    position: Mapped[int] = mapped_column(Integer)


class NoteFile(UserOwned, Base):
    """A file of notes of the session, in the user's space of object storage (ADR-0012)."""

    __tablename__ = "note_file"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_session.id", "study_session.user_id"],
            ondelete="CASCADE",
        ),
        # Never another user's or session's file, whoever wrote the row.
        CheckConstraint(
            "object_key LIKE 'users/' || user_id || '/sessions/' || session_id || '/notes/'"
            " || sha256 || '.%'",
            name="object_key_is_notes_key",
        ),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        CheckConstraint(one_of("mime", NOTE_MIMES), name="mime_known"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        # The same file twice in a session is one note (US-02 AC13).
        UniqueConstraint("session_id", "sha256"),
    )

    session_id: Mapped[uuid.UUID]
    object_key: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(Integer)


class NoteUpload(UserOwned, Base):
    """A note file whose upload URL was signed and that no confirmed session holds yet.

    Counts against the account's note quota while the file is on its way, and tells the cleanup
    job what to delete if it never is confirmed. Confirming the session turns it into a
    `note_file` and deletes this row.
    """

    __tablename__ = "note_upload"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_session.id", "study_session.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "object_key LIKE 'users/' || user_id || '/sessions/' || session_id || '/notes/'"
            " || sha256 || '.%'",
            name="object_key_is_notes_key",
        ),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        CheckConstraint(one_of("mime", NOTE_MIMES), name="mime_known"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        UniqueConstraint("session_id", "sha256"),
        Index(None, "presigned_at"),
    )

    session_id: Mapped[uuid.UUID]
    object_key: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # When the last URL was signed: cleanup waits until it is long dead.
    presigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
