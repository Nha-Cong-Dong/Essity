"""question_generation and pg_trgm

For T9.6b (US-17 AC1, AC3): `pg_trgm` for the near-duplicate check of a generated question against
the stored ones (`similarity()`), and `question_generation`, the one-running-row-per-target guard
that keeps a double click from generating two sets.

No trigram index: the check always filters by user and subject first (a few hundred rows at most),
so `similarity()` over that set is cheap and an index would only serve the `%` operator. The
extension is created with IF NOT EXISTS and never dropped by the downgrade: other objects may use
it, and dropping it is not needed to undo this revision.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-02 09:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "question_generation",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("target_kind", sa.String(length=8), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=7), server_default="running", nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_kind IN ('question', 'section', 'type')",
            name=op.f("ck_question_generation_target_kind_known"),
        ),
        sa.CheckConstraint(
            "status IN ('done', 'running')", name=op.f("ck_question_generation_status_known")
        ),
        sa.ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subject.id", "subject.user_id"],
            name=op.f("fk_question_generation_subject_id_subject"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_question_generation_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_generation")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_question_generation_id_user_id")),
    )
    op.create_index(
        op.f("ix_question_generation_user_id"), "question_generation", ["user_id"], unique=False
    )
    op.create_index(
        "uq_question_generation_running",
        "question_generation",
        ["user_id", "subject_id", "target_kind", "target_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.add_column("question", sa.Column("generation_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_question_generation_id"), "question", ["generation_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_question_generation_id_question_generation"),
        "question",
        "question_generation",
        ["generation_id", "user_id"],
        ["id", "user_id"],
        ondelete="SET NULL (generation_id)",
    )


def downgrade() -> None:
    """Downgrade schema. The extension stays: other objects may use it."""
    op.drop_constraint(
        op.f("fk_question_generation_id_question_generation"), "question", type_="foreignkey"
    )
    op.drop_index(op.f("ix_question_generation_id"), table_name="question")
    op.drop_column("question", "generation_id")
    op.drop_index(
        "uq_question_generation_running",
        table_name="question_generation",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index(op.f("ix_question_generation_user_id"), table_name="question_generation")
    op.drop_table("question_generation")
