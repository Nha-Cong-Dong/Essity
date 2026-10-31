"""v2_schema_group2

Group 2 of the v2 data model (ARCH §6.2, ADR-0008: additions only): the practice schedule
(practice_state, practice_log), the command log, the card-to-card edges (unit_edge), the
question-bank link on question, and 'default' as a question type's reference origin. Old rows keep
their shape; the downgrade refuses rather than delete learner data.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-31 07:00:00.000000

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = ("practice_state", "practice_log", "command_log", "unit_edge")
# Written out, not imported: a later change to the models must not change what this ran.
OLD_ORIGINS = "'learner_median', 'rubric', 'user'"
NEW_ORIGINS = "'default', 'learner_median', 'rubric', 'user'"
NOT_BLANK = (
    "raw_text ~ '[^ \\t\\n\\v\\f\\r\\u0085\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]'"  # noqa: E501
)

# practice_log follows review_log: the same refusal function, so T2.22 (core_eraser) replaces it
# once for both. command_log is not history of review: it may be deleted with its subject or its
# user, and it changes once, applied -> undone, nothing else.
GUARDS = """
CREATE TRIGGER practice_log_append_only BEFORE UPDATE OR DELETE ON practice_log
  FOR EACH ROW EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER practice_log_no_truncate BEFORE TRUNCATE ON practice_log
  FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse();

CREATE FUNCTION command_log_guard() RETURNS trigger LANGUAGE plpgsql
  SET search_path = public, pg_temp AS $$
BEGIN
  IF OLD.status <> 'applied' OR NEW.status <> 'undone' OR NEW.undone_at IS NULL
     OR NEW.id <> OLD.id OR NEW.user_id <> OLD.user_id OR NEW.created_at <> OLD.created_at
     OR NEW.subject_id IS DISTINCT FROM OLD.subject_id
     OR NEW.screen_session_id IS DISTINCT FROM OLD.screen_session_id
     OR NEW.raw_text <> OLD.raw_text
     OR NEW.ops_json <> OLD.ops_json OR NEW.inverse_json <> OLD.inverse_json
     OR NEW.affected_count <> OLD.affected_count
     OR NEW.run_id IS DISTINCT FROM OLD.run_id OR NEW.seq <> OLD.seq THEN
    RAISE EXCEPTION 'UPDATE on command_log is refused: a command is only undone, once'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER command_log_guard BEFORE UPDATE ON command_log
  FOR EACH ROW EXECUTE FUNCTION command_log_guard();
"""


def _owned_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "practice_state",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("phase", sa.String(length=10), nullable=False),
        sa.Column("step", sa.SmallInteger(), nullable=True),
        sa.Column("stability", sa.Float(precision=53), nullable=False),
        sa.Column("difficulty", sa.Float(precision=53), nullable=False),
        sa.Column("due", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        *_owned_columns(),
        sa.CheckConstraint(
            "phase IN ('relearning', 'review')", name=op.f("ck_practice_state_phase_known")
        ),
        sa.CheckConstraint(
            "(phase = 'relearning') = (step IS NOT NULL)",
            name=op.f("ck_practice_state_step_when_relearning"),
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "user_id"],
            ["question.id", "question.user_id"],
            name=op.f("fk_practice_state_question_id_question"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_practice_state_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_practice_state")),
        sa.UniqueConstraint(
            "user_id", "question_id", name=op.f("uq_practice_state_user_id_question_id")
        ),
    )
    op.create_index(op.f("ix_practice_state_user_id"), "practice_state", ["user_id"])
    op.create_index(
        "ix_practice_state_user_id_due",
        "practice_state",
        ["user_id", "due"],
        postgresql_where=sa.text("removed_at IS NULL"),
    )

    op.create_table(
        "practice_log",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grade_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        *_owned_columns(),
        sa.CheckConstraint("rating IN (1, 2, 3, 4)", name=op.f("ck_practice_log_rating_known")),
        sa.ForeignKeyConstraint(
            ["grade_id", "user_id"],
            ["grade.id", "grade.user_id"],
            name=op.f("fk_practice_log_grade_id_grade"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "user_id"],
            ["question.id", "question.user_id"],
            name=op.f("fk_practice_log_question_id_question"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_practice_log_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_practice_log")),
        sa.UniqueConstraint("grade_id", name=op.f("uq_practice_log_grade_id")),
    )
    op.create_index(op.f("ix_practice_log_question_id"), "practice_log", ["question_id"])
    op.create_index(op.f("ix_practice_log_user_id"), "practice_log", ["user_id"])
    op.create_index(
        op.f("ix_practice_log_user_id_reviewed_at_seq"),
        "practice_log",
        ["user_id", "reviewed_at", "seq"],
    )

    op.create_table(
        "command_log",
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("screen_session_id", sa.Uuid(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("ops_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inverse_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=7), server_default="applied", nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        *_owned_columns(),
        sa.CheckConstraint(
            "affected_count >= 0", name=op.f("ck_command_log_affected_not_negative")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(inverse_json) = 'array'", name=op.f("ck_command_log_inverse_is_array")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(ops_json) = 'array'", name=op.f("ck_command_log_ops_is_array")
        ),
        sa.CheckConstraint(NOT_BLANK, name=op.f("ck_command_log_raw_text_not_blank")),
        sa.CheckConstraint(
            "status IN ('applied', 'undone')", name=op.f("ck_command_log_status_known")
        ),
        sa.CheckConstraint(
            "(status = 'undone') = (undone_at IS NOT NULL)",
            name=op.f("ck_command_log_undone_has_time"),
        ),
        sa.ForeignKeyConstraint(
            ["subject_id", "user_id"],
            ["subject.id", "subject.user_id"],
            name=op.f("fk_command_log_subject_id_subject"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_command_log_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_command_log")),
    )
    op.create_index(op.f("ix_command_log_user_id"), "command_log", ["user_id"])
    op.create_index(
        "ix_command_log_user_id_subject_id_seq",
        "command_log",
        ["user_id", "subject_id", sa.text("seq DESC")],
    )

    op.create_table(
        "unit_edge",
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("src_unit_id", sa.Uuid(), nullable=False),
        sa.Column("dst_unit_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("origin", sa.String(length=4), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        *_owned_columns(),
        sa.CheckConstraint(
            "origin = 'user' OR jsonb_array_length(evidence) >= 1",
            name=op.f("ck_unit_edge_ai_has_evidence"),
        ),
        sa.CheckConstraint(
            "kind <> 'contrast' OR src_unit_id < dst_unit_id",
            name=op.f("ck_unit_edge_contrast_one_way"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'array'", name=op.f("ck_unit_edge_evidence_is_array")
        ),
        sa.CheckConstraint(
            "kind IN ('applies_to', 'contrast', 'example_of', 'part_of', 'prerequisite')",
            name=op.f("ck_unit_edge_kind_known"),
        ),
        sa.CheckConstraint("src_unit_id <> dst_unit_id", name=op.f("ck_unit_edge_not_to_itself")),
        sa.CheckConstraint("origin IN ('ai', 'user')", name=op.f("ck_unit_edge_origin_known")),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'proposed', 'rejected')",
            name=op.f("ck_unit_edge_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["dst_unit_id", "subject_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.subject_id", "knowledge_unit.user_id"],
            name=op.f("fk_unit_edge_dst_unit_id_knowledge_unit"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["src_unit_id", "subject_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.subject_id", "knowledge_unit.user_id"],
            name=op.f("fk_unit_edge_src_unit_id_knowledge_unit"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_unit_edge_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_edge")),
        sa.UniqueConstraint(
            "src_unit_id",
            "dst_unit_id",
            "kind",
            name=op.f("uq_unit_edge_src_unit_id_dst_unit_id_kind"),
        ),
    )
    op.create_index(op.f("ix_unit_edge_dst_unit_id"), "unit_edge", ["dst_unit_id"])
    op.create_index(op.f("ix_unit_edge_subject_id_status"), "unit_edge", ["subject_id", "status"])
    op.create_index(op.f("ix_unit_edge_user_id"), "unit_edge", ["user_id"])

    op.add_column(
        "doc_section",
        sa.Column("studied_weight", sa.Float(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_doc_section_studied_weight_not_negative"),
        "doc_section",
        "studied_weight >= 0 AND studied_weight < 'Infinity'",
    )
    op.add_column("question", sa.Column("bank_document_id", sa.Uuid(), nullable=True))
    op.add_column("question", sa.Column("bank_ord", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_question_bank_document_id_document"),
        "question",
        "document",
        ["bank_document_id", "subject_id", "user_id"],
        ["id", "subject_id", "user_id"],
        ondelete="NO ACTION",
    )
    op.create_check_constraint(
        op.f("ck_question_bank_ord_needs_document"),
        "question",
        "bank_ord IS NULL OR bank_document_id IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_question_bank_ord_not_negative"), "question", "bank_ord IS NULL OR bank_ord >= 0"
    )
    op.create_index(
        op.f("ix_question_bank_document_id_bank_ord"),
        "question",
        ["bank_document_id", "bank_ord"],
    )

    op.drop_constraint(op.f("ck_question_type_ref_origin_known"), "question_type", type_="check")
    op.create_check_constraint(
        op.f("ck_question_type_ref_origin_known"), "question_type", f"ref_origin IN ({NEW_ORIGINS})"
    )
    op.execute(GUARDS)


def downgrade() -> None:
    """Downgrade schema: refuses, and changes nothing, while a row only 0025 can hold is left."""
    bind = op.get_bind()
    for table in NEW_TABLES:
        held = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608
        if held:
            raise RuntimeError(f"0025 downgrade: {held} {table} row(s) would be lost")
    defaults = bind.execute(
        sa.text("SELECT count(*) FROM question_type WHERE ref_origin = 'default'")
    ).scalar_one()
    if defaults:
        raise RuntimeError(f"0025 downgrade: {defaults} question_type row(s) have origin 'default'")
    linked = bind.execute(
        sa.text("SELECT count(*) FROM question WHERE bank_document_id IS NOT NULL")
    ).scalar_one()
    if linked:
        raise RuntimeError(f"0025 downgrade: {linked} question(s) are linked to a question bank")

    studied = bind.execute(
        sa.text("SELECT count(*) FROM doc_section WHERE studied_weight <> 0")
    ).scalar_one()
    if studied:
        raise RuntimeError(f"0025 downgrade: {studied} doc_section row(s) have studied_weight")
    op.drop_constraint(op.f("ck_question_type_ref_origin_known"), "question_type", type_="check")
    op.create_check_constraint(
        op.f("ck_question_type_ref_origin_known"), "question_type", f"ref_origin IN ({OLD_ORIGINS})"
    )
    op.drop_constraint(
        op.f("ck_doc_section_studied_weight_not_negative"), "doc_section", type_="check"
    )
    op.drop_column("doc_section", "studied_weight")
    op.drop_index(op.f("ix_question_bank_document_id_bank_ord"), table_name="question")
    op.drop_constraint(op.f("ck_question_bank_ord_not_negative"), "question", type_="check")
    op.drop_constraint(op.f("ck_question_bank_ord_needs_document"), "question", type_="check")
    op.drop_constraint(
        op.f("fk_question_bank_document_id_document"), "question", type_="foreignkey"
    )
    op.drop_column("question", "bank_ord")
    op.drop_column("question", "bank_document_id")

    # Their triggers go with the tables; append_only_refuse() belongs to 0008 and stays.
    op.drop_table("unit_edge")
    op.drop_table("command_log")
    op.execute("DROP FUNCTION command_log_guard()")
    op.drop_table("practice_log")
    op.drop_table("practice_state")
