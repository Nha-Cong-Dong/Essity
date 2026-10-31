"""T7.6, migration 0024, an edge the tester added (ADR-0008): the downgrade refuses, with its own
message, while a `submission.created.v1` event is still in the outbox."""

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text


def test_downgrade_refuses_while_a_submission_event_is_in_the_outbox(
    engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: the downgrade does not look for queued v2 events first (it then dies on the
    # narrowed event_type CHECK, or, with the CHECK gone too, drops an event ai-service owes).
    event_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO outbox (id, user_id, event_type, payload, trace_context,"
                " occurred_at, available_at) VALUES (:id, :u, 'submission.created.v1',"
                " '{}'::jsonb, '{}'::jsonb, now(), now())"
            ),
            {"id": event_id, "u": uuid.uuid4()},
        )
    try:
        with pytest.raises(RuntimeError, match="0024 downgrade: 1 submission.created.v1"):
            command.downgrade(alembic_cfg, "0023")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM outbox WHERE id = :id"), {"id": event_id}
                ).scalar_one()
                == 1
            )
    finally:
        command.upgrade(alembic_cfg, "head")
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM outbox WHERE id = :id"), {"id": event_id})
