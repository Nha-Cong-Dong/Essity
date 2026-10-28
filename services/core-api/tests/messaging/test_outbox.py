"""T4.2 (ADR-0006): `enqueue_event` writes an event into the `outbox` table in the caller's
transaction, so saved data and its event are committed, or rolled back, together."""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from opentelemetry import trace
from pydantic import ValidationError
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models import Outbox
from core_api.messaging.envelope import DocumentUploaded, SessionProcessed, UserDeleted
from core_api.messaging.outbox import enqueue_event

pytestmark = pytest.mark.usefixtures("clean_outbox")

NOW = datetime(2026, 10, 25, 8, 30, tzinfo=UTC)


def uploaded(user_id: uuid.UUID) -> DocumentUploaded:
    return DocumentUploaded(
        document_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        object_key=f"users/{user_id}/subjects/{uuid.uuid4()}/raw/a.pdf",
    )


def row(engine: Engine, event_id: uuid.UUID) -> Outbox | None:
    with Session(engine) as session:
        return session.get(Outbox, event_id)


def test_committed_event_is_in_the_outbox(engine: Engine) -> None:
    # Red when: enqueue_event writes nothing, or writes columns the relay cannot rebuild the
    # envelope from.
    user_id = uuid.uuid4()
    payload = uploaded(user_id)
    with Session(engine) as session:
        event_id = enqueue_event(session, payload, user_id=user_id, now=NOW)
        session.commit()
    saved = row(engine, event_id)
    assert saved is not None
    assert (saved.user_id, saved.event_type) == (user_id, "document.uploaded.v1")
    assert saved.payload == payload.model_dump(mode="json")
    assert (saved.occurred_at, saved.available_at) == (NOW, NOW)
    assert (saved.sent_at, saved.attempts, saved.last_error) == (None, 0, None)


def test_rollback_leaves_no_event(engine: Engine) -> None:
    # Red when: the event is written outside the caller's transaction (its own session or a
    # commit), so a rolled-back save still sends an event (T4.2 "Xong khi").
    user_id = uuid.uuid4()
    with Session(engine) as session:
        event_id = enqueue_event(session, uploaded(user_id), user_id=user_id, now=NOW)
        session.rollback()
    assert row(engine, event_id) is None


def test_envelope_without_user_id_refused(engine: Engine) -> None:
    # Red when: an event can reach the outbox without the user it belongs to (ADR-0006: every
    # event carries user_id; T6.3 deletes by it).
    with Session(engine) as session:
        with pytest.raises(ValidationError):
            enqueue_event(session, UserDeleted(), user_id=None, now=NOW)  # pyright: ignore[reportArgumentType]
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO outbox (id, event_type, payload, trace_context, occurred_at,"
                " available_at) VALUES (gen_random_uuid(), 'user.deleted.v1', '{}', '{}',"
                " now(), now())"
            )
        )


def test_enqueue_refuses_an_event_core_api_does_not_send(engine: Engine) -> None:
    # Red when: core-api can put an ai → core event on its own stream (plan G1).
    with Session(engine) as session, pytest.raises(ValueError, match="session.processed.v1"):
        payload = SessionProcessed(
            study_session_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            result_key=f"users/{uuid.uuid4()}/r.json",
        )
        # The type checker refuses it too; this is the guard at run time.
        enqueue_event(session, payload, user_id=uuid.uuid4(), now=NOW)  # pyright: ignore[reportArgumentType]


def test_outbox_check_refuses_an_ai_to_core_type(engine: Engine) -> None:
    # Red when: the CHECK on event_type lets through a type core-api does not send (plan G1).
    with engine.connect() as connection, pytest.raises(IntegrityError, match="event_type"):
        connection.execute(
            text(
                "INSERT INTO outbox (id, user_id, event_type, payload, trace_context,"
                " occurred_at, available_at) VALUES (gen_random_uuid(), gen_random_uuid(),"
                " 'session.processed.v1', '{}', '{}', now(), now())"
            )
        )


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 25, 8, 30),
        datetime(2026, 10, 25, 15, 30, tzinfo=timezone(timedelta(hours=7))),
    ],
    ids=["naive", "plus-07"],
)
def test_enqueue_refuses_a_time_that_is_not_utc(engine: Engine, now: datetime) -> None:
    # Red when: an event is stored with a time the contract refuses.
    with Session(engine) as session, pytest.raises(ValidationError):
        enqueue_event(session, UserDeleted(), user_id=uuid.uuid4(), now=now)


def test_enqueue_event_records_current_traceparent(engine: Engine) -> None:
    # Red when: the producer's trace context is not stored, so the consumer's span cannot be
    # linked to the request that caused the event (ADR-0013, plan Y7).
    tracer = trace.get_tracer("tests.outbox")
    with Session(engine) as session:
        with tracer.start_as_current_span("save") as span:
            inside = enqueue_event(session, UserDeleted(), user_id=uuid.uuid4(), now=NOW)
        outside = enqueue_event(session, UserDeleted(), user_id=uuid.uuid4(), now=NOW)
        session.commit()
    context = span.get_span_context()
    saved_inside, saved_outside = row(engine, inside), row(engine, outside)
    assert saved_inside is not None and saved_outside is not None
    flags = int(context.trace_flags)
    traceparent = f"00-{context.trace_id:032x}-{context.span_id:016x}-{flags:02x}"
    assert saved_inside.trace_context == {"traceparent": traceparent}
    assert saved_outside.trace_context == {}


def test_0014_up_down_up(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: 0014's downgrade leaves the table behind, or its upgrade misses the partial index
    # the relay reads through.
    try:
        command.downgrade(alembic_cfg, "0010")
        assert "outbox" not in inspect(engine).get_table_names()
        command.upgrade(alembic_cfg, "0014")
        with engine.connect() as connection:
            index = connection.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_outbox_unsent'")
            ).scalar_one()
        assert "(available_at, seq)" in index
        assert "WHERE (sent_at IS NULL)" in index
    finally:
        command.upgrade(alembic_cfg, "head")


def test_seq_orders_rows_in_insert_order(engine: Engine) -> None:
    # Red when: seq is not filled by the database in insert order (the relay sends by seq).
    with Session(engine) as session:
        ids = [enqueue_event(session, UserDeleted(), user_id=uuid.uuid4(), now=NOW) for _ in "abc"]
        session.commit()
        seqs = session.scalars(select(Outbox.seq).where(Outbox.id.in_(ids)).order_by(Outbox.seq))
        by_seq = session.scalars(select(Outbox.id).where(Outbox.id.in_(ids)).order_by(Outbox.seq))
        assert len(set(seqs)) == 3
        assert list(by_seq) == ids
