import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, not_blank, one_of

# pending: a URL was signed, the file is not confirmed yet. uploaded: confirmed, the event sent.
# rejected: the file stored was not the PDF declared; its object is gone, the row stays (and
# counts against the quota) until cleanup, so the URL cannot store it again unseen (plan R1).
# T4.8 adds indexed/failed by swapping the CHECK.
DOCUMENT_STATUSES = frozenset({"pending", "uploaded", "rejected"})


class Document(UserOwned, Base):
    """A reference file of a subject (US-01, T4.5): a PDF in object storage at its raw key.

    One row per file and subject: the same file again is the same document (US-02 AC13). Never
    deduplicated across subjects or users: the key is in the user's and the subject's space.
    """

    __tablename__ = "document"
    __table_args__ = (
        # (subject_id, user_id) -> subject(id, user_id): never a document on another user's
        # subject.
        ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subject.id", "subject.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("subject_id", "sha256"),
        # Target of composite foreign keys to come (anchor, session_range).
        UniqueConstraint("id", "user_id"),
        Index(None, "user_id", "status"),
        # What the cleanup job reads: uploads never confirmed, or refused, by age.
        Index(
            "ix_document_unconfirmed",
            "presigned_at",
            postgresql_where=text("status <> 'uploaded'"),
        ),
        CheckConstraint(one_of("status", DOCUMENT_STATUSES), name="status_known"),
        CheckConstraint(not_blank("short_name"), name="short_name_not_blank"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        # The key is the row's own raw key (ADR-0012), whoever wrote it: never another user's
        # or subject's file, never derived/.
        CheckConstraint(
            "object_key = 'users/' || user_id || '/subjects/' || subject_id"
            " || '/raw/' || sha256 || '.pdf'",
            name="object_key_is_raw_key",
        ),
        CheckConstraint(
            "(status = 'uploaded') = (uploaded_at IS NOT NULL)", name="uploaded_at_iff_uploaded"
        ),
        CheckConstraint("page_count IS NULL OR page_count >= 1", name="page_count_from_one"),
    )

    subject_id: Mapped[uuid.UUID]
    short_name: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    object_key: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(10))
    # When the last upload URL was signed: cleanup waits until it is long dead.
    presigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_count: Mapped[int | None] = mapped_column(Integer)  # set by T4.8
