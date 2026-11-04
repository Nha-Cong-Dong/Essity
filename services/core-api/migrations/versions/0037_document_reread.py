"""document_reread

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-05 09:00:00.000000

OUTLINE-FIX3: the learner asked to read a document's outline again. `reread` is `pending` while
ai-service reads and `failed` when it could not; the document keeps its state and its outline.
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
    op.add_column("document", sa.Column("reread", sa.String(length=7), nullable=True))
    op.create_check_constraint(
        op.f("ck_document_reread_known"),
        "document",
        "reread IS NULL OR reread IN ('pending', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_document_reread_known"), "document", type_="check")
    op.drop_column("document", "reread")
