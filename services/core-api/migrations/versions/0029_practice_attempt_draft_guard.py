"""practice_attempt_draft_guard

For T8.4 (T7.M5 review, PLAN T8.4; US-16 AC2/AC5): a practice attempt has no review session, so
UNIQUE(review_session_id, question_id) lets NULL sessions repeat and cannot stop two concurrent
"open the question" requests from creating two drafts. A partial unique index closes that: one
open draft per user and question while no review session is involved. A CHECK makes the server's
`served_at` mandatory for a practice attempt (the active time is measured from it). A submitted
practice attempt is never covered by the index, so a question can be practised again.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-01 15:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_attempt_one_practice_draft"
CHECK = "ck_attempt_practice_has_served_at"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        INDEX,
        "attempt",
        ["user_id", "question_id"],
        unique=True,
        postgresql_where="review_session_id IS NULL AND status = 'draft'",
    )
    op.create_check_constraint(
        op.f(CHECK), "attempt", "review_session_id IS NOT NULL OR served_at IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f(CHECK), "attempt", type_="check")
    op.drop_index(INDEX, table_name="attempt")
