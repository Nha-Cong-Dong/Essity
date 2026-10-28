"""document indexed

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-28 09:00:00.000000

T4.8: ai-service's answer to a confirmed document. `indexed` keeps the keys of the files it wrote
under `derived/{run_id}/` (the table of contents is read from there, not copied), `failed` keeps
a reason code. Both are confirmed files, so they hold `uploaded_at` and are never cleaned up: the
cleanup index now names the two unconfirmed states instead of "not uploaded".
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXED = (
    "(status = 'indexed') = (run_id IS NOT NULL AND toc_key IS NOT NULL"
    " AND page_labels_key IS NOT NULL AND page_text_key IS NOT NULL"
    " AND thumbnails_prefix IS NOT NULL AND page_count IS NOT NULL)"
)


def upgrade() -> None:
    op.add_column("document", sa.Column("run_id", sa.Uuid(), nullable=True))
    for name in ("toc_key", "page_labels_key", "page_text_key", "thumbnails_prefix"):
        op.add_column("document", sa.Column(name, sa.String(length=1024), nullable=True))
    op.add_column(
        "document",
        sa.Column(
            "unreadable_pages",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column("document", sa.Column("failure_reason", sa.String(length=20), nullable=True))

    op.drop_constraint(op.f("ck_document_status_known"), "document", type_="check")
    op.create_check_constraint(
        op.f("ck_document_status_known"),
        "document",
        "status IN ('failed', 'indexed', 'pending', 'rejected', 'uploaded')",
    )
    op.drop_constraint(op.f("ck_document_uploaded_at_iff_uploaded"), "document", type_="check")
    op.create_check_constraint(
        op.f("ck_document_uploaded_at_iff_uploaded"),
        "document",
        "(status NOT IN ('pending', 'rejected')) = (uploaded_at IS NOT NULL)",
    )
    op.create_check_constraint(op.f("ck_document_indexed_iff_derived"), "document", _INDEXED)
    op.create_check_constraint(
        op.f("ck_document_failed_iff_reason"),
        "document",
        "(status = 'failed') = (failure_reason IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_document_failure_reason_known"),
        "document",
        "failure_reason IN ('internal_error', 'too_large', 'unreadable', 'unsupported')",
    )
    op.drop_index(
        "ix_document_unconfirmed",
        table_name="document",
        postgresql_where=sa.text("status <> 'uploaded'"),
    )
    op.create_index(
        "ix_document_unconfirmed",
        "document",
        ["presigned_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'rejected')"),
    )


def downgrade() -> None:
    # Indexed and failed documents are confirmed files: back to `uploaded`, their results dropped.
    op.execute("UPDATE document SET status = 'uploaded' WHERE status IN ('indexed', 'failed')")
    op.drop_index(
        "ix_document_unconfirmed",
        table_name="document",
        postgresql_where=sa.text("status IN ('pending', 'rejected')"),
    )
    op.create_index(
        "ix_document_unconfirmed",
        "document",
        ["presigned_at"],
        unique=False,
        postgresql_where=sa.text("status <> 'uploaded'"),
    )
    for name in (
        "ck_document_failure_reason_known",
        "ck_document_failed_iff_reason",
        "ck_document_indexed_iff_derived",
    ):
        op.drop_constraint(op.f(name), "document", type_="check")
    op.drop_constraint(op.f("ck_document_uploaded_at_iff_uploaded"), "document", type_="check")
    op.create_check_constraint(
        op.f("ck_document_uploaded_at_iff_uploaded"),
        "document",
        "(status = 'uploaded') = (uploaded_at IS NOT NULL)",
    )
    op.drop_constraint(op.f("ck_document_status_known"), "document", type_="check")
    op.create_check_constraint(
        op.f("ck_document_status_known"),
        "document",
        "status IN ('pending', 'rejected', 'uploaded')",
    )
    for name in (
        "failure_reason",
        "unreadable_pages",
        "thumbnails_prefix",
        "page_text_key",
        "page_labels_key",
        "toc_key",
        "run_id",
    ):
        op.drop_column("document", name)
