"""Tables of database `ai`: the audit log of AI work (ADR-0010, ARCH §6.3).

Nothing here is business data (ARCH §7.2): grades live in core. `pipeline_run` is one run of a
task for one request; `llm_call` is one call to a model (or to the fake grader) inside it,
written whether the call succeeded or failed, with the input and output as sent and received.
That makes `llm_call` the one place an answer is stored on this side; application logs never
carry it (ADR-0013).

`user_id` and `subject_id` are core's ids. There is no foreign key: they live in another
database.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, SmallInteger, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ai_service.db.base import Base, one_of

TASKS = frozenset(
    {"grade", "extract_session", "chunk_units", "generate_questions", "parse_command"}
)
PROVIDERS = frozenset({"anthropic", "fake"})
RUN_STATUSES = frozenset({"running", "succeeded", "failed"})


class PipelineRun(Base):
    __tablename__ = "pipeline_run"
    __table_args__ = (
        CheckConstraint(one_of("task", TASKS), name="task_known"),
        CheckConstraint(one_of("status", RUN_STATUSES), name="status_known"),
        CheckConstraint("prompt_sha256 ~ '^[0-9a-f]{64}$'", name="prompt_sha256_hex"),
        Index(None, "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID]
    subject_id: Mapped[uuid.UUID]
    attempt_id: Mapped[uuid.UUID | None]
    task: Mapped[str]
    prompt_version: Mapped[str]
    # SHA-256 of the prompt template as loaded: tells two edits of the same version apart.
    prompt_sha256: Mapped[str]
    status: Mapped[str] = mapped_column(default="running", server_default="running")
    # A stable code (grade_invalid, llm_unavailable, ...), never an exception message.
    error_code: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LlmCall(Base):
    __tablename__ = "llm_call"
    __table_args__ = (
        CheckConstraint(one_of("task", TASKS), name="task_known"),
        CheckConstraint(one_of("provider", PROVIDERS), name="provider_known"),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
        CheckConstraint("cost_usd >= 0", name="cost_not_negative"),
        CheckConstraint("input_tokens >= 0", name="input_tokens_not_negative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_not_negative"),
        CheckConstraint("latency_ms >= 0", name="latency_not_negative"),
        # T2.11 sums a user's cost over a day and a month.
        Index(None, "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # RESTRICT: a run with calls cannot be deleted, so paid calls never vanish with it.
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_run.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID]
    subject_id: Mapped[uuid.UUID]
    task: Mapped[str]
    provider: Mapped[str]
    model: Mapped[str]
    prompt_version: Mapped[str]
    # 1 for the first call of a run, 2 for the retry after an output that broke the rules.
    attempt: Mapped[int] = mapped_column(SmallInteger)
    # The request as sent (system, messages, schema) and the model's text as received.
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output: Mapped[str | None]
    # The provider's own reason (end_turn, max_tokens, refusal, ...): tells an output cut short
    # from a malformed one.
    stop_reason: Mapped[str | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    # Exact: summed per user for quotas (T2.11). USD, six decimals.
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int]
    # A stable code (provider_error, timeout, invalid_output, ...), never an exception message.
    error_code: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmReservation(Base):
    """Money set aside for a call that has been admitted and not yet recorded (T2.11).

    The quota guard writes one under a per-user lock, before the call, so two requests at once
    cannot both see "nothing spent". It is deleted in the same transaction as the `llm_call` row
    that records the real cost. If the spend cannot be recorded it is kept (`expires_at` moved
    to the end of the month): the money may have been spent. A process that dies mid-call
    leaves one that expires by itself.
    """

    __tablename__ = "llm_reservation"
    __table_args__ = (
        CheckConstraint("amount_usd >= 0", name="amount_not_negative"),
        Index(None, "user_id", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID]
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProcessedEvent(Base):
    """An event a consumer has handled (T4.3, ADR-0006: delivery is at least once).

    The consumer inserts the row in the same transaction as the handler's own writes, so the
    two commit or roll back together: a redelivered event finds the row and is skipped. Ids
    only: nothing here belongs to a user, so deleting a user (T6.3) leaves this table alone.
    """

    __tablename__ = "processed_event"

    # The consumer group (`ai-service`): another group reading the same stream claims apart.
    consumer: Mapped[str] = mapped_column(primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
