"""document

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-26 01:33:49.321841

T4.5 (ADR-0012): a subject's reference files. The object key is checked to be the row's own raw
key, so no row can point at another user's or subject's file. `rejected` rows stay until the
cleanup job, after their upload URL is long dead (plan R1). The partial index is what the job
reads.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Copied from core_api.db.base.not_blank, so this migration stays as written when the code moves.
_WHITESPACE = r" \t\n\v\f\r\u0085   -     　"


def _not_blank(column: str) -> str:
    return f"{column} ~ '[^{_WHITESPACE}]'"


def upgrade() -> None:
    op.create_table(
        "document",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("short_name", sa.String(length=200), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("presigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'uploaded') = (uploaded_at IS NOT NULL)",
            name=op.f("ck_document_uploaded_at_iff_uploaded"),
        ),
        sa.CheckConstraint(
            "object_key = 'users/' || user_id || '/subjects/' || subject_id"
            " || '/raw/' || sha256 || '.pdf'",
            name=op.f("ck_document_object_key_is_raw_key"),
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_document_sha256_hex")),
        sa.CheckConstraint(_not_blank("short_name"), name=op.f("ck_document_short_name_not_blank")),
        sa.CheckConstraint(
            "status IN ('pending', 'rejected', 'uploaded')", name=op.f("ck_document_status_known")
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 1", name=op.f("ck_document_page_count_from_one")
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_document_size_positive")),
        sa.ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subject.id", "subject.user_id"],
            name=op.f("fk_document_subject_id_subject"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_document_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_document_id_user_id")),
        sa.UniqueConstraint("subject_id", "sha256", name=op.f("uq_document_subject_id_sha256")),
    )
    op.create_index(
        "ix_document_unconfirmed",
        "document",
        ["presigned_at"],
        unique=False,
        postgresql_where=sa.text("status <> 'uploaded'"),
    )
    op.create_index(op.f("ix_document_user_id"), "document", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_document_user_id_status"), "document", ["user_id", "status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_user_id_status"), table_name="document")
    op.drop_index(op.f("ix_document_user_id"), table_name="document")
    op.drop_index(
        "ix_document_unconfirmed",
        table_name="document",
        postgresql_where=sa.text("status <> 'uploaded'"),
    )
    op.drop_table("document")
