"""attempt_practice_link

For T8.4 (ARCH §6.2, ADR-0008: additions only): a practice attempt belongs to no review session,
so `attempt.review_session_id` becomes nullable. UNIQUE(review_session_id, question_id) stays:
NULLs are distinct, so a question can be practised again and again, while a review attempt is
still one per session and question. `attempt_guard` compares the two keys with IS DISTINCT FROM:
`<>` against NULL is NULL, which would let a key change to or from NULL unseen. The downgrade
refuses while a practice attempt exists, and puts back the guard of 0008.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-01 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out, not imported: a later change to the models must not change what this ran.
GUARD_NEW = """
CREATE OR REPLACE FUNCTION attempt_guard() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
  IF TG_OP = 'DELETE' OR OLD.status <> 'draft'
     OR NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at
     OR NEW.user_id <> OLD.user_id
     OR NEW.review_session_id IS DISTINCT FROM OLD.review_session_id
     OR NEW.question_id IS DISTINCT FROM OLD.question_id THEN
    RAISE EXCEPTION '% on attempt is refused: only a draft changes, never its keys', TG_OP
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;
"""
GUARD_OLD = GUARD_NEW.replace(" IS DISTINCT FROM ", " <> ")  # exactly the function of 0008


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("attempt", "review_session_id", existing_type=sa.Uuid(), nullable=True)
    op.execute(GUARD_NEW)


def downgrade() -> None:
    """Downgrade schema: refuses while a practice attempt exists."""
    held = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM attempt WHERE review_session_id IS NULL"))
        .scalar_one()
    )
    if held:
        raise RuntimeError(f"0028 downgrade: {held} attempt(s) belong to no review session")
    op.execute(GUARD_OLD)
    op.alter_column("attempt", "review_session_id", existing_type=sa.Uuid(), nullable=False)
