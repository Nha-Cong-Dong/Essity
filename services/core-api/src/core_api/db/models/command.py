import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core_api.db.base import Base, UserOwned, not_blank, one_of

COMMAND_STATUSES = frozenset({"applied", "undone"})


class CommandLog(UserOwned, Base):
    """A typed command applied to the learner's cards (T9.2): the text, what it did and the
    inverse that undoes it. Not review history: it goes with its subject and its user. A trigger
    lets a row change once, from applied to undone."""

    __tablename__ = "command_log"
    __table_args__ = (
        # NULL subject: a command on all subjects. Never another user's subject.
        ForeignKeyConstraint(
            ["subject_id", "user_id"], ["subject.id", "subject.user_id"], ondelete="CASCADE"
        ),
        CheckConstraint(not_blank("raw_text"), name="raw_text_not_blank"),
        CheckConstraint("jsonb_typeof(ops_json) = 'array'", name="ops_is_array"),
        CheckConstraint("jsonb_typeof(inverse_json) = 'array'", name="inverse_is_array"),
        CheckConstraint(one_of("status", COMMAND_STATUSES), name="status_known"),
        CheckConstraint("affected_count >= 0", name="affected_not_negative"),
        CheckConstraint("(status = 'undone') = (undone_at IS NOT NULL)", name="undone_has_time"),
        Index(
            "ix_command_log_user_id_subject_id_seq",
            "user_id",
            "subject_id",
            text("seq DESC"),
        ),
    )

    subject_id: Mapped[uuid.UUID | None]
    # One screen session: "undo" reverses the commands of that session, newest first.
    screen_session_id: Mapped[uuid.UUID | None]
    raw_text: Mapped[str] = mapped_column(Text)
    ops_json: Mapped[Any] = mapped_column(JSONB)
    inverse_json: Mapped[Any] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(7), default="applied", server_default="applied")
    affected_count: Mapped[int] = mapped_column(Integer)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[uuid.UUID | None]  # pipeline run in the ai database: no foreign key
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
