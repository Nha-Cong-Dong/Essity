"""review_history

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23 05:10:24.083537

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Restoring a backup (ADR-0012, T2.20): restore schema and data together (pg_restore without
# --data-only), which creates these triggers after the data. A data-only restore into a migrated
# database runs the BEFORE INSERT triggers on every row and fails on grade_unit (its grades are
# old): use --disable-triggers, which needs a superuser. Every test that adds a grade_unit also
# checks that grade.created_at is the database's now(), never set by the ORM (review 668d501).
#
# The append-only rules of layer 3 (ARCH §6.1, ADR-0012, plan D1/D5/D8, review plan P1). BEFORE
# ... FOR EACH ROW also catches INSERT ... ON CONFLICT DO UPDATE and the deletes of a cascade:
# there is no way around them yet, not even deleting the account; T6.3 opens one for a database
# role of its own (CREATE OR REPLACE FUNCTION).
GUARDS = """
CREATE FUNCTION append_only_refuse() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% on % is refused: review history is append-only', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE FUNCTION attempt_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' OR OLD.status <> 'draft'
     OR NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at
     OR NEW.user_id <> OLD.user_id
     OR NEW.review_session_id <> OLD.review_session_id
     OR NEW.question_id <> OLD.question_id THEN
    RAISE EXCEPTION '% on attempt is refused: only a draft changes, never its keys', TG_OP
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;

CREATE FUNCTION review_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' OR OLD.ended_at IS NOT NULL
     OR NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at
     OR NEW.user_id <> OLD.user_id
     OR NEW.learning_day <> OLD.learning_day
     OR NEW.started_at <> OLD.started_at THEN
    RAISE EXCEPTION '% on review_session is refused: a session changes only until it ends', TG_OP
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;

-- Only a submitted attempt is graded (review 31074ea): a draft could still change under its grade.
CREATE FUNCTION grade_needs_submitted_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM attempt WHERE id = NEW.attempt_id AND status = 'submitted') THEN
    RAISE EXCEPTION 'INSERT on grade is refused: the attempt is not submitted'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;

-- A grade's verdicts are written with it, in its transaction; a later judgement is a new grade.
CREATE FUNCTION grade_unit_with_its_grade() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM grade WHERE id = NEW.grade_id AND created_at = now()) THEN
    RAISE EXCEPTION 'INSERT on grade_unit is refused: verdicts go with a new grade'
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER grade_needs_submitted_attempt BEFORE INSERT ON grade
  FOR EACH ROW EXECUTE FUNCTION grade_needs_submitted_attempt();
CREATE TRIGGER grade_unit_with_its_grade BEFORE INSERT ON grade_unit
  FOR EACH ROW EXECUTE FUNCTION grade_unit_with_its_grade();

CREATE TRIGGER grade_append_only BEFORE UPDATE OR DELETE ON grade
  FOR EACH ROW EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER grade_unit_append_only BEFORE UPDATE OR DELETE ON grade_unit
  FOR EACH ROW EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER review_log_append_only BEFORE UPDATE OR DELETE ON review_log
  FOR EACH ROW EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER attempt_guard BEFORE UPDATE OR DELETE ON attempt
  FOR EACH ROW EXECUTE FUNCTION attempt_guard();
CREATE TRIGGER review_session_guard BEFORE UPDATE OR DELETE ON review_session
  FOR EACH ROW EXECUTE FUNCTION review_session_guard();

CREATE TRIGGER grade_no_truncate BEFORE TRUNCATE ON grade
  FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER grade_unit_no_truncate BEFORE TRUNCATE ON grade_unit
  FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER review_log_no_truncate BEFORE TRUNCATE ON review_log
  FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER attempt_no_truncate BEFORE TRUNCATE ON attempt
  FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse();
CREATE TRIGGER review_session_no_truncate BEFORE TRUNCATE ON review_session
  FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse();
"""

DROP_GUARDS = """
DROP FUNCTION append_only_refuse() CASCADE;
DROP FUNCTION attempt_guard() CASCADE;
DROP FUNCTION review_session_guard() CASCADE;
DROP FUNCTION grade_needs_submitted_attempt() CASCADE;
DROP FUNCTION grade_unit_with_its_grade() CASCADE;
"""


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "review_session",
        sa.Column("learning_day", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.String(length=20), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stop_reason IS NULL OR stop_reason IN ('completed', 'user_stopped')",
            name=op.f("ck_review_session_stop_reason_known"),
        ),
        sa.CheckConstraint(
            "(ended_at IS NULL) = (stop_reason IS NULL)",
            name=op.f("ck_review_session_ended_with_reason"),
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name=op.f("ck_review_session_ends_after_start"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_review_session_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_session")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_review_session_id_user_id")),
    )
    op.create_index(op.f("ix_review_session_user_id"), "review_session", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_review_session_user_id_learning_day"),
        "review_session",
        ["user_id", "learning_day"],
        unique=False,
    )
    op.create_table(
        "attempt",
        sa.Column("review_session_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answer_text", sa.Text(), server_default="", nullable=False),
        sa.Column("dont_remember", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(length=10), server_default="draft", nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'submitted') = (submitted_at IS NOT NULL)",
            name=op.f("ck_attempt_submitted_has_time"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted')", name=op.f("ck_attempt_status_known")
        ),
        sa.CheckConstraint(
            "char_length(answer_text) <= 20000", name=op.f("ck_attempt_answer_length")
        ),
        sa.ForeignKeyConstraint(
            ["question_id", "user_id"],
            ["question.id", "question.user_id"],
            name=op.f("fk_attempt_question_id_question"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["review_session_id", "user_id"],
            ["review_session.id", "review_session.user_id"],
            name=op.f("fk_attempt_review_session_id_review_session"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_attempt_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempt")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_attempt_id_user_id")),
        sa.UniqueConstraint(
            "review_session_id",
            "question_id",
            name=op.f("uq_attempt_review_session_id_question_id"),
        ),
    )
    op.create_index(op.f("ix_attempt_question_id"), "attempt", ["question_id"], unique=False)
    op.create_index(op.f("ix_attempt_user_id"), "attempt", ["user_id"], unique=False)
    op.create_table(
        "memory_state",
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("facet", sa.String(length=20), server_default="core", nullable=False),
        sa.Column("phase", sa.String(length=10), nullable=False),
        sa.Column("step", sa.SmallInteger(), nullable=True),
        sa.Column("stability", sa.Float(precision=53), nullable=False),
        sa.Column("difficulty", sa.Float(precision=53), nullable=False),
        sa.Column("due", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(phase = 'relearning') = (step IS NOT NULL)",
            name=op.f("ck_memory_state_step_when_relearning"),
        ),
        sa.CheckConstraint("facet IN ('core')", name=op.f("ck_memory_state_facet_known")),
        sa.CheckConstraint(
            "phase IN ('relearning', 'review')", name=op.f("ck_memory_state_phase_known")
        ),
        sa.ForeignKeyConstraint(
            ["unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            name=op.f("fk_memory_state_unit_id_knowledge_unit"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_memory_state_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_state")),
        sa.UniqueConstraint(
            "user_id", "unit_id", "facet", name=op.f("uq_memory_state_user_id_unit_id_facet")
        ),
    )
    op.create_index(op.f("ix_memory_state_user_id"), "memory_state", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_memory_state_user_id_due"), "memory_state", ["user_id", "due"], unique=False
    )
    op.create_table(
        "grade",
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("overall", sa.String(length=10), nullable=False),
        sa.Column("understanding", sa.SmallInteger(), nullable=True),
        sa.Column(
            "missing",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "anchors_used",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(overall = 'forgot') = (source = 'system')", name=op.f("ck_grade_forgot_by_system")
        ),
        sa.CheckConstraint(
            "overall IN ('correct', 'forgot', 'incorrect', 'partial')",
            name=op.f("ck_grade_overall_known"),
        ),
        sa.CheckConstraint(
            "source IN ('ai', 'system', 'user_override')", name=op.f("ck_grade_source_known")
        ),
        sa.CheckConstraint(
            "understanding IS NULL OR (overall NOT IN ('incorrect', 'forgot')"
            " AND understanding BETWEEN 0 AND 3)",
            name=op.f("ck_grade_understanding_when_right"),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id", "user_id"],
            ["attempt.id", "attempt.user_id"],
            name=op.f("fk_grade_attempt_id_attempt"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_grade_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grade")),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_grade_id_user_id")),
    )
    op.create_index(op.f("ix_grade_attempt_id_seq"), "grade", ["attempt_id", "seq"], unique=False)
    op.create_index(op.f("ix_grade_user_id"), "grade", ["user_id"], unique=False)
    op.create_table(
        "grade_unit",
        sa.Column("grade_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", sa.String(length=10), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "verdict IN ('correct', 'incorrect', 'partial')",
            name=op.f("ck_grade_unit_verdict_known"),
        ),
        sa.ForeignKeyConstraint(
            ["grade_id", "user_id"],
            ["grade.id", "grade.user_id"],
            name=op.f("fk_grade_unit_grade_id_grade"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            name=op.f("fk_grade_unit_unit_id_knowledge_unit"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_grade_unit_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grade_unit")),
        sa.UniqueConstraint(
            "grade_id", "unit_id", "user_id", name=op.f("uq_grade_unit_grade_id_unit_id_user_id")
        ),
        sa.UniqueConstraint("grade_id", "unit_id", name=op.f("uq_grade_unit_grade_id_unit_id")),
    )
    op.create_index(op.f("ix_grade_unit_unit_id"), "grade_unit", ["unit_id"], unique=False)
    op.create_index(op.f("ix_grade_unit_user_id"), "grade_unit", ["user_id"], unique=False)
    op.create_table(
        "review_log",
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("facet", sa.String(length=20), server_default="core", nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grade_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("facet IN ('core')", name=op.f("ck_review_log_facet_known")),
        sa.CheckConstraint("rating IN (1, 2, 3)", name=op.f("ck_review_log_rating_known")),
        sa.ForeignKeyConstraint(
            ["grade_id", "unit_id", "user_id"],
            ["grade_unit.grade_id", "grade_unit.unit_id", "grade_unit.user_id"],
            name=op.f("fk_review_log_grade_id_grade_unit"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id", "user_id"],
            ["knowledge_unit.id", "knowledge_unit.user_id"],
            name=op.f("fk_review_log_unit_id_knowledge_unit"),
            ondelete="NO ACTION",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_review_log_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_log")),
        sa.UniqueConstraint(
            "grade_id", "unit_id", "facet", name=op.f("uq_review_log_grade_id_unit_id_facet")
        ),
    )
    op.create_index(op.f("ix_review_log_grade_id"), "review_log", ["grade_id"], unique=False)
    op.create_index(
        op.f("ix_review_log_unit_id_facet"), "review_log", ["unit_id", "facet"], unique=False
    )
    op.create_index(op.f("ix_review_log_user_id"), "review_log", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_review_log_user_id_reviewed_at_seq"),
        "review_log",
        ["user_id", "reviewed_at", "seq"],
        unique=False,
    )
    # ### end Alembic commands ###
    op.execute(GUARDS)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(DROP_GUARDS)  # functions and their triggers, before the tables
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_review_log_user_id_reviewed_at_seq"), table_name="review_log")
    op.drop_index(op.f("ix_review_log_user_id"), table_name="review_log")
    op.drop_index(op.f("ix_review_log_unit_id_facet"), table_name="review_log")
    op.drop_index(op.f("ix_review_log_grade_id"), table_name="review_log")
    op.drop_table("review_log")
    op.drop_index(op.f("ix_grade_unit_user_id"), table_name="grade_unit")
    op.drop_index(op.f("ix_grade_unit_unit_id"), table_name="grade_unit")
    op.drop_table("grade_unit")
    op.drop_index(op.f("ix_grade_user_id"), table_name="grade")
    op.drop_index(op.f("ix_grade_attempt_id_seq"), table_name="grade")
    op.drop_table("grade")
    op.drop_index(op.f("ix_memory_state_user_id_due"), table_name="memory_state")
    op.drop_index(op.f("ix_memory_state_user_id"), table_name="memory_state")
    op.drop_table("memory_state")
    op.drop_index(op.f("ix_attempt_user_id"), table_name="attempt")
    op.drop_index(op.f("ix_attempt_question_id"), table_name="attempt")
    op.drop_table("attempt")
    op.drop_index(op.f("ix_review_session_user_id_learning_day"), table_name="review_session")
    op.drop_index(op.f("ix_review_session_user_id"), table_name="review_session")
    op.drop_table("review_session")
    # ### end Alembic commands ###
