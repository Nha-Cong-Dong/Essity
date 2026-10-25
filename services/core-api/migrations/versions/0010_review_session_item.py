"""review_session_item

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-25 12:00:00.000000

T2.9: the questions of a review session, fixed when it starts (plan C1), append-only like the
rest of layer 3 through the same `append_only_refuse()` (plan C3; T2.22 replaces that function
for core_eraser, so this table follows). One open session per learning day (plan C4).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GUARDS = """
CREATE TRIGGER review_session_item_append_only BEFORE UPDATE OR DELETE ON review_session_item
  FOR EACH ROW EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER review_session_item_no_truncate BEFORE TRUNCATE ON review_session_item
  FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse();
"""


def upgrade() -> None:
    op.create_table(
        "review_session_item",
        sa.Column("review_session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_review_session_item_position_from_one")),
        sa.ForeignKeyConstraint(
            ["question_id", "user_id"],
            ["question.id", "question.user_id"],
            name=op.f("fk_review_session_item_question_id_question"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["review_session_id", "user_id"],
            ["review_session.id", "review_session.user_id"],
            name=op.f("fk_review_session_item_review_session_id_review_session"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_review_session_item_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_session_item")),
        sa.UniqueConstraint(
            "review_session_id",
            "position",
            name=op.f("uq_review_session_item_review_session_id_position"),
        ),
        sa.UniqueConstraint(
            "review_session_id",
            "question_id",
            name=op.f("uq_review_session_item_review_session_id_question_id"),
        ),
    )
    op.create_index(
        op.f("ix_review_session_item_question_id"), "review_session_item", ["question_id"]
    )
    op.create_index(op.f("ix_review_session_item_user_id"), "review_session_item", ["user_id"])
    op.create_index(
        "uq_review_session_open_per_day",
        "review_session",
        ["user_id", "learning_day"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.execute(GUARDS)


def downgrade() -> None:
    op.drop_index("uq_review_session_open_per_day", table_name="review_session")
    op.drop_table("review_session_item")
