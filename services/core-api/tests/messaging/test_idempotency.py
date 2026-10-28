"""T4.4 (ADR-0006): `claim` records that a consumer handled an event, in the handler's own
transaction, so an event delivered twice is handled once."""

import uuid
from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session

from core_api.db.models import ProcessedEvent
from core_api.messaging.idempotency import claim

NOW = datetime(2026, 10, 26, 8, 30, tzinfo=UTC)


def claimed(engine: Engine, consumer: str, event_id: uuid.UUID) -> bool:
    with Session(engine) as session:
        return session.get(ProcessedEvent, (consumer, event_id)) is not None


def test_first_claim_wins_and_the_second_does_not(engine: Engine) -> None:
    # Red when: a claim does not record the event, or a second claim of it also returns True
    # (the handler would run twice).
    event_id = uuid.uuid4()
    with Session(engine) as session, session.begin():
        assert claim(session, consumer="core-api", event_id=event_id, now=NOW) is True
    with Session(engine) as session, session.begin():
        assert claim(session, consumer="core-api", event_id=event_id, now=NOW) is False
    with Session(engine) as session:
        row = session.scalars(
            select(ProcessedEvent).where(ProcessedEvent.event_id == event_id)
        ).one()
        assert (row.consumer, row.processed_at) == ("core-api", NOW)


def test_claims_are_per_consumer(engine: Engine) -> None:
    # Red when: the key is the event alone, so a second consumer of the same event skips it.
    event_id = uuid.uuid4()
    with Session(engine) as session, session.begin():
        assert claim(session, consumer="core-api", event_id=event_id, now=NOW)
        assert claim(session, consumer="core-api.other", event_id=event_id, now=NOW)


def test_rolled_back_claim_is_not_kept(engine: Engine) -> None:
    # Red when: claim commits on its own, so a handler that failed after it is never run again.
    event_id = uuid.uuid4()
    with Session(engine) as session:
        assert claim(session, consumer="core-api", event_id=event_id, now=NOW)
        session.rollback()
    assert not claimed(engine, "core-api", event_id)


def test_0015_up_down_up(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: 0015's downgrade leaves the table behind or its upgrade does not create it.
    try:
        command.downgrade(alembic_cfg, "0014")
        assert "processed_event" not in inspect(engine).get_table_names()
        command.upgrade(alembic_cfg, "0015")
        assert "processed_event" in inspect(engine).get_table_names()
    finally:
        command.upgrade(alembic_cfg, "head")
