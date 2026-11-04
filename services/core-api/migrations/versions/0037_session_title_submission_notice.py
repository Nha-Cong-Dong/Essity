"""session title and submission notice

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-05 09:00:00.000000

CARDS-V3 (05/11): the session is named by the topic of its cards (`study_session.title`, chosen
by ai-service; null for older sessions, which fall back to the first words of the note), and a
submission that ended with no card says why (`submission.notice`, a closed list). Schema only:
the cards of old drafts are moved to the vault by `core_api.cli promote-drafts`, which runs
the same code a save does (events, review question, ledger), not by SQL here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0037"
down_revision: str | Sequence[str] | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("study_session", sa.Column("title", sa.String(length=200), nullable=True))
    op.add_column("submission", sa.Column("notice", sa.String(length=32), nullable=True))
    op.create_check_constraint(
        op.f("ck_submission_notice_known"),
        "submission",
        "notice IS NULL OR notice IN ('no_content_found')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_submission_notice_known"), "submission", type_="check")
    op.drop_column("submission", "notice")
    op.drop_column("study_session", "title")
