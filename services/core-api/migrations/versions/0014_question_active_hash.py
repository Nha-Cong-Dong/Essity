"""question_active_hash

Revision ID: 0014
Revises: 0011
Create Date: 2026-10-26 09:00:00.000000

T2.2: a seeded question whose answer changes is replaced, not edited (decision with flow-expert,
26/10): the old one is retired, so what was graded against it stays true, and a new one takes its
place. The content hash is therefore unique among the ACTIVE questions of a subject only
(`UNIQUE ... WHERE status = 'active'`); retired questions may repeat it.

down_revision is the head of this branch; it moves to main's head when the branch is rebased.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "uq_question_user_id_subject_id_content_hash"
NEW = "uq_question_active_content_hash"


def upgrade() -> None:
    op.drop_constraint(OLD, "question", type_="unique")
    op.create_index(
        NEW,
        "question",
        ["user_id", "subject_id", "content_hash"],
        unique=True,
        postgresql_where="status = 'active'",
    )


def downgrade() -> None:
    # Fails loudly when a replaced question left two rows with one hash: the old rule cannot
    # hold them, and choosing which to drop is not a migration's call.
    op.drop_index(NEW, table_name="question")
    op.create_unique_constraint(OLD, "question", ["user_id", "subject_id", "content_hash"])
