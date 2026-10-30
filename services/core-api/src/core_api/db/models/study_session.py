import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, not_blank, one_of

SESSION_STATUSES = frozenset({"draft", "confirmed"})
# How the first extraction ended: a card to confirm (proposed), a question back (clarify), notes
# only (note_only), or no card (failed / disabled / quota / no_documents): the manual form.
EXTRACTIONS = frozenset(
    {"proposed", "note_only", "clarify", "failed", "disabled", "quota", "no_documents"}
)
# How processing a confirmed session stands (T4.18): no state yet means waiting for ai-service.
PROCESSING_STATES = frozenset({"processing", "processed", "failed"})
PROCESSING_STEPS = frozenset({"reading_notes", "splitting_units", "anchoring", "writing_questions"})
PROCESSING_REASONS = frozenset({"unreadable", "llm_unavailable", "internal_error"})
DEPTHS = frozenset({"deep", "skim", "unclear"})
NOTE_MIMES = frozenset(
    {"image/jpeg", "image/png", "application/pdf", "text/plain", "text/markdown"}
)
# What a v2 submission may also hold (T7.6): the rows keep this wider set; v1 confirm still takes
# only NOTE_MIMES.
SUBMISSION_MIMES = NOTE_MIMES | {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
DESCRIPTION_MAX = 2000
FILE_KEYS_MAX = 20


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
        CheckConstraint(
            "processing_state IS NULL OR status = 'confirmed'", name="processing_needs_confirmed"
        ),
        CheckConstraint(
            one_of("processing_state", PROCESSING_STATES),
            name="processing_state_known",
        ),
        CheckConstraint(
            one_of("processing_step", PROCESSING_STEPS),
            name="processing_step_known",
        ),
        CheckConstraint(
            one_of("processing_reason", PROCESSING_REASONS),
            name="processing_reason_known",
        ),
        CheckConstraint(
            "processing_percent IS NULL OR processing_percent BETWEEN 0 AND 100",
            name="processing_percent_range",
        ),
    )

    subject_id: Mapped[uuid.UUID]
    description_raw: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft")
    extraction: Mapped[str] = mapped_column(String(14))
    studied_on: Mapped[date | None] = mapped_column(Date)
    learning_day: Mapped[date | None] = mapped_column(Date)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # T4.18: from session.progress / processed / failed. processed and failed are terminal.
    processing_state: Mapped[str | None] = mapped_column(String(10))
    processing_step: Mapped[str | None] = mapped_column(String(17))
    processing_percent: Mapped[int | None] = mapped_column(SmallInteger)
    processing_reason: Mapped[str | None] = mapped_column(String(16))


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
        CheckConstraint(one_of("mime", SUBMISSION_MIMES), name="mime_known"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        # The same file twice in a session is one note (US-02 AC13).
        UniqueConstraint("session_id", "sha256"),
    )

    session_id: Mapped[uuid.UUID]
    object_key: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(100))
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
        CheckConstraint(one_of("mime", SUBMISSION_MIMES), name="mime_known"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        UniqueConstraint("session_id", "sha256"),
        Index(None, "presigned_at"),
    )

    session_id: Mapped[uuid.UUID]
    object_key: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # When the last URL was signed: cleanup waits until it is long dead.
    presigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# queued: stored, waiting for ai-service. pending_ai: the AI quota is spent, tried again when there
# is some (spec v2 §16.3). failed / done end it.
SUBMISSION_STATUSES = frozenset({"queued", "processing", "pending_ai", "failed", "done"})


# Every key is `users/<user>/sessions/<session>/notes/<sha256>.<ext>` of this very row, and at most
# FILE_KEYS_MAX of them, none NULL. A CHECK cannot hold a subquery, so the keys are joined with
# commas and matched whole by one anchored regex (a key has no comma, so none can hide in another).
_KEY_RE = (
    "'users/' || user_id || '/sessions/' || session_id"
    r" || '/notes/[0-9a-f]{64}\.(jpg|png|pdf|txt|md|docx|pptx)'"
)
FILE_KEYS_SQL = (
    f"cardinality(file_keys) <= {FILE_KEYS_MAX} AND array_position(file_keys, NULL) IS NULL"
    f" AND array_to_string(file_keys, ',') ~ ('^(' || {_KEY_RE} || '(,' || {_KEY_RE} || ')*)?$')"
)


class Submission(UserOwned, Base):
    """What the learner handed in for a study session (T7.1, spec v2 §16.2): the files are stored
    before they are processed, so a failure or a spent quota never loses them.

    `file_keys` holds only this session's own note keys (CHECK, migration 0024).
    """

    __tablename__ = "submission"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_session.id", "study_session.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "user_id"),
        Index(None, "session_id"),
        # What the retry job reads.
        Index(
            "ix_submission_waiting",
            "created_at",
            postgresql_where=text("status IN ('queued', 'pending_ai')"),
        ),
        CheckConstraint(one_of("status", SUBMISSION_STATUSES), name="status_known"),
        CheckConstraint(
            "(status IN ('done', 'failed')) = (finished_at IS NOT NULL)",
            name="finished_iff_ended",
        ),
        CheckConstraint(FILE_KEYS_SQL, name="file_keys_are_own_notes"),
    )

    session_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(10))
    file_keys: Mapped[list[str]] = mapped_column(ARRAY(String(1024)), server_default=text("'{}'"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
