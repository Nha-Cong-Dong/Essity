"""submission_contract

T7.6 (ADR-0008, additions only): the page positions of a section (`first_page`, `last_page`),
the submission's own file keys (CHECK), and the DOCX and PPTX types a note file may hold. Old rows
keep their shape; the downgrade refuses rather than delete a DOCX or PPTX note.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-30 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTE_TABLES = ("note_file", "note_upload")
# Written out, not imported: a later change to the models must not change what this ran.
OLD_MIMES = "'application/pdf', 'image/jpeg', 'image/png', 'text/markdown', 'text/plain'"
NEW_MIMES = (
    "'application/pdf',"
    " 'application/vnd.openxmlformats-officedocument.presentationml.presentation',"
    " 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',"
    " 'image/jpeg', 'image/png', 'text/markdown', 'text/plain'"
)

_KEY = (
    "'users/' || user_id || '/sessions/' || session_id"
    r" || '/notes/[0-9a-f]{64}\.(jpg|png|pdf|txt|md|docx|pptx)'"
)
FILE_KEYS_SQL = (
    "cardinality(file_keys) <= 20 AND array_position(file_keys, NULL) IS NULL"
    f" AND array_to_string(file_keys, ',') ~ ('^(' || {_KEY} || '(,' || {_KEY} || ')*)?$')"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("doc_section", sa.Column("first_page", sa.Integer(), nullable=True))
    op.add_column("doc_section", sa.Column("last_page", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_doc_section_pages_both_or_neither"),
        "doc_section",
        "(first_page IS NULL) = (last_page IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_doc_section_pages_ordered"),
        "doc_section",
        "first_page >= 1 AND last_page >= first_page",
    )
    for table in NOTE_TABLES:
        op.alter_column(
            table, "mime", type_=sa.String(length=100), existing_type=sa.String(length=20)
        )
        op.drop_constraint(op.f(f"ck_{table}_mime_known"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_mime_known"), table, f"mime IN ({NEW_MIMES})")
    op.create_check_constraint(
        op.f("ck_submission_file_keys_are_own_notes"), "submission", FILE_KEYS_SQL
    )


def downgrade() -> None:
    """Downgrade schema: refuses while a DOCX or PPTX note exists."""
    connection = op.get_bind()
    for table in NOTE_TABLES:
        held = connection.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE mime NOT IN ({OLD_MIMES})")  # noqa: S608
        ).scalar_one()
        if held:
            raise RuntimeError(f"0024 downgrade: {held} {table} row(s) hold a DOCX or PPTX file")
    op.drop_constraint(op.f("ck_submission_file_keys_are_own_notes"), "submission", type_="check")
    for table in NOTE_TABLES:
        op.drop_constraint(op.f(f"ck_{table}_mime_known"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_mime_known"), table, f"mime IN ({OLD_MIMES})")
        op.alter_column(
            table, "mime", type_=sa.String(length=20), existing_type=sa.String(length=100)
        )
    op.drop_constraint(op.f("ck_doc_section_pages_ordered"), "doc_section", type_="check")
    op.drop_constraint(op.f("ck_doc_section_pages_both_or_neither"), "doc_section", type_="check")
    op.drop_column("doc_section", "last_page")
    op.drop_column("doc_section", "first_page")
