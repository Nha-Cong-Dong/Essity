"""note_upload

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-29 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "note_upload",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime", sa.String(length=20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("presigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mime IN ('application/pdf', 'image/jpeg', 'image/png', 'text/markdown', 'text/plain')",
            name=op.f("ck_note_upload_mime_known"),
        ),
        sa.CheckConstraint(
            "object_key LIKE 'users/' || user_id || '/sessions/' || session_id || '/notes/'"
            " || sha256 || '.%%'",
            name=op.f("ck_note_upload_object_key_is_notes_key"),
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_note_upload_sha256_hex")),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_note_upload_size_positive")),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_session.id", "study_session.user_id"],
            name=op.f("fk_note_upload_session_id_study_session"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_note_upload_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_upload")),
        sa.UniqueConstraint("session_id", "sha256", name=op.f("uq_note_upload_session_id_sha256")),
    )
    op.create_index(op.f("ix_note_upload_presigned_at"), "note_upload", ["presigned_at"])
    op.create_index(op.f("ix_note_upload_user_id"), "note_upload", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_note_upload_user_id"), table_name="note_upload")
    op.drop_index(op.f("ix_note_upload_presigned_at"), table_name="note_upload")
    op.drop_table("note_upload")
