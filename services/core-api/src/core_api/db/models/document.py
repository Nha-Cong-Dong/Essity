import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, not_blank, one_of

# pending: a URL was signed, the file is not confirmed yet. uploaded: confirmed, the event sent.
# rejected: the file stored was not the PDF declared; its object is gone, the row stays (and
# counts against the quota) until cleanup, so the URL cannot store it again unseen (plan R1).
# indexed / failed (T4.8): ai-service's answer to `document.uploaded.v1`; the file is confirmed
# in both, so they hold `uploaded_at` too.
DOCUMENT_STATUSES = frozenset({"pending", "uploaded", "rejected", "indexed", "failed"})
UNCONFIRMED = ("pending", "rejected")
FAILURE_REASONS = frozenset({"unreadable", "unsupported", "too_large", "internal_error"})
# v2 (T7.1): what a file is for in its subject, and what it is made of. One textbook per subject.
DOCUMENT_ROLES = frozenset({"textbook", "question_bank", "auxiliary"})
DOCUMENT_FORMATS = frozenset({"pdf", "docx", "pptx", "image"})


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
        # Target of the composite foreign key of doc_section (never a section of another subject).
        UniqueConstraint("id", "subject_id", "user_id"),
        Index(None, "user_id", "status"),
        Index(
            "uq_document_textbook_per_subject",
            "subject_id",
            unique=True,
            postgresql_where=text("role = 'textbook'"),
        ),
        # What the cleanup job reads: uploads never confirmed, or refused, by age.
        Index(
            "ix_document_unconfirmed",
            "presigned_at",
            postgresql_where=text("status IN ('pending', 'rejected')"),
        ),
        CheckConstraint(one_of("status", DOCUMENT_STATUSES), name="status_known"),
        CheckConstraint(one_of("role", DOCUMENT_ROLES), name="role_known"),
        CheckConstraint(one_of("format", DOCUMENT_FORMATS), name="format_known"),
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
            "(status NOT IN ('pending', 'rejected')) = (uploaded_at IS NOT NULL)",
            name="uploaded_at_iff_uploaded",
        ),
        CheckConstraint(
            "(status = 'indexed') = (run_id IS NOT NULL AND toc_key IS NOT NULL"
            " AND page_labels_key IS NOT NULL AND page_text_key IS NOT NULL"
            " AND thumbnails_prefix IS NOT NULL AND page_count IS NOT NULL)",
            name="indexed_iff_derived",
        ),
        CheckConstraint(
            "(status = 'failed') = (failure_reason IS NOT NULL)", name="failed_iff_reason"
        ),
        CheckConstraint(one_of("failure_reason", FAILURE_REASONS), name="failure_reason_known"),
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
    # Set by T4.8 from ai-service's answer. The files are keys under `derived/{run_id}/` (ADR-0012);
    # core never copies their content, the table of contents is read from `toc_key` on request.
    page_count: Mapped[int | None] = mapped_column(Integer)
    run_id: Mapped[uuid.UUID | None]
    toc_key: Mapped[str | None] = mapped_column(String(1024))
    page_labels_key: Mapped[str | None] = mapped_column(String(1024))
    page_text_key: Mapped[str | None] = mapped_column(String(1024))
    thumbnails_prefix: Mapped[str | None] = mapped_column(String(1024))
    # Pages with no text to read (scans), 1-based: the web offers reading them as images.
    unreadable_pages: Mapped[list[int]] = mapped_column(ARRAY(Integer), server_default=text("'{}'"))
    failure_reason: Mapped[str | None] = mapped_column(String(20))
    # Old rows are auxiliary PDFs: a subject may already hold several files, so none is promoted.
    role: Mapped[str] = mapped_column(String(14), server_default="auxiliary")
    format: Mapped[str] = mapped_column(String(5), server_default="pdf")


# How a section's `weight` is counted, and where the section came from (spec v2 §16.1 Q-D).
SECTION_UNITS = frozenset({"page", "slide", "est_page"})
SECTION_SOURCES = frozenset({"bookmark", "heading", "llm_toc", "chunk10", "user"})


class DocSection(UserOwned, Base):
    """A node of a document's outline (T7.1, spec v2 §16.2): the tree progress and "what to study
    next" are counted on. `weight` is in `unit`s; an excluded section is left out of the count.

    The parent is in the same document, and so the same subject and user: the foreign key says so.
    `ord` is not unique among siblings: moving sections about passes through repeats.
    """

    __tablename__ = "doc_section"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "subject_id", "user_id"],
            ["document.id", "document.subject_id", "document.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["parent_id", "document_id", "user_id"],
            ["doc_section.id", "doc_section.document_id", "doc_section.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "user_id"),
        UniqueConstraint("id", "document_id", "user_id"),
        # Target of the composite foreign keys of unit_section and question_section.
        UniqueConstraint("id", "subject_id", "user_id"),
        Index(None, "document_id", "parent_id", "ord"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_its_own_parent"),
        CheckConstraint("ord >= 0", name="ord_not_negative"),
        CheckConstraint("weight >= 0", name="weight_not_negative"),
        CheckConstraint(not_blank("title"), name="title_not_blank"),
        CheckConstraint(one_of("unit", SECTION_UNITS), name="unit_known"),
        CheckConstraint(one_of("source", SECTION_SOURCES), name="source_known"),
    )

    subject_id: Mapped[uuid.UUID]
    document_id: Mapped[uuid.UUID]
    parent_id: Mapped[uuid.UUID | None]
    ord: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    weight: Mapped[float] = mapped_column(Float, server_default="1")
    unit: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(8))
    excluded: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
