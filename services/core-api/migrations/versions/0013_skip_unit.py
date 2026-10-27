"""skip_unit

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-28 09:00:00.000000

T2.23: a unit the user skips ("không cần ôn phần này") gets `skipped_at`, orthogonal to `status`;
schedule and review history are not touched (ADR-0008). A session started for one subject
remembers it (`review_session.subject_id`), so the question that replaces a skipped one comes
from the same subject. The session guard refuses to change it, like its other keys.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GUARD = """
CREATE OR REPLACE FUNCTION review_session_guard() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
  IF TG_OP = 'DELETE' OR OLD.ended_at IS NOT NULL
     OR NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at
     OR NEW.user_id <> OLD.user_id
     OR NEW.learning_day <> OLD.learning_day
     OR NEW.started_at <> OLD.started_at{extra} THEN
    RAISE EXCEPTION '% on review_session is refused: a session changes only until it ends', TG_OP
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;
"""


def upgrade() -> None:
    op.add_column("knowledge_unit", sa.Column("skipped_at", sa.DateTime(timezone=True)))
    op.add_column("review_session", sa.Column("subject_id", sa.Uuid()))
    op.create_foreign_key(
        op.f("fk_review_session_subject_id_subject"),
        "review_session",
        "subject",
        ["subject_id", "user_id"],
        ["id", "user_id"],
        ondelete="NO ACTION",
    )
    op.execute(GUARD.format(extra="\n     OR NEW.subject_id IS DISTINCT FROM OLD.subject_id"))


def downgrade() -> None:
    op.execute(GUARD.format(extra=""))
    op.drop_constraint(
        op.f("fk_review_session_subject_id_subject"), "review_session", type_="foreignkey"
    )
    op.drop_column("review_session", "subject_id")
    op.drop_column("knowledge_unit", "skipped_at")
