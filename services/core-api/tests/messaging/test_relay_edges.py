"""Edge cases of the outbox and relay found by the tester's second mutation run (T4.2, PR #38):
a failed send of a whole batch, the trace context on the wire, and the outbox CHECK against every
ai → core type of the contract. Real PostgreSQL and Redis.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import cast

import pytest
from opentelemetry import trace
from redis import Redis
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.clients.redis import redis_from_url
from core_api.db.models import Outbox
from core_api.messaging.consumer import EVENT_TYPES
from core_api.messaging.envelope import UserDeleted
from core_api.messaging.outbox import enqueue_event
from core_api.messaging.relay import relay_once

pytestmark = pytest.mark.usefixtures("clean_outbox")

NOW = datetime(2026, 10, 28, 8, 30, tzinfo=UTC)
CORE_TO_AI = {
    "document.uploaded.v1",
    "session.confirmed.v1",
    "grade.requested.v1",
    "user.deleted.v1",
}


def _enqueue(engine: Engine) -> uuid.UUID:
    with Session(engine) as session:
        event_id = enqueue_event(session, UserDeleted(), user_id=uuid.uuid4(), now=NOW)
        session.commit()
    return event_id


def test_redis_down_backs_off_every_row_of_the_batch(engine: Engine, stream: str) -> None:
    # Red when: a failed send pushes back only some rows of the batch: the others keep
    # attempts 0 and stay due, so the relay hammers a Redis that is down with them every second.
    ids = [_enqueue(engine) for _ in range(3)]
    dead = redis_from_url("redis://127.0.0.1:9/0", timeout=0.2)
    assert relay_once(engine, dead, now=NOW, stream=stream) == 0
    with Session(engine) as session:
        rows = [session.get(Outbox, i) for i in ids]
    assert all(row is not None for row in rows)
    assert [(r.sent_at, r.attempts) for r in rows if r] == [(None, 1)] * 3
    assert all(r.available_at > NOW for r in rows if r)


def test_relayed_envelope_carries_the_producer_trace(
    engine: Engine, redis_client: Redis, stream: str
) -> None:
    # Red when: the relay rebuilds the envelope without the row's trace_context, so the
    # consumer's span starts a new trace instead of continuing the request's (ADR-0013, Y7).
    tracer = trace.get_tracer("tests.relay_edges")
    with Session(engine) as session, tracer.start_as_current_span("save") as span:
        enqueue_event(session, UserDeleted(), user_id=uuid.uuid4(), now=NOW)
        session.commit()
    context = span.get_span_context()
    traceparent = (
        f"00-{context.trace_id:032x}-{context.span_id:016x}-{int(context.trace_flags):02x}"
    )
    assert relay_once(engine, redis_client, now=NOW, stream=stream) == 1
    [(_, fields)] = cast(list[tuple[bytes, dict[bytes, bytes]]], redis_client.xrange(stream))
    assert json.loads(fields[b"envelope"])["trace_context"]["traceparent"] == traceparent


@pytest.mark.parametrize("event_type", sorted(EVENT_TYPES - CORE_TO_AI))
def test_outbox_check_refuses_every_ai_to_core_type(engine: Engine, event_type: str) -> None:
    # Red when: migration 0014's CHECK lets in any type core-api does not send (plan G1), e.g.
    # an ai → core type added to its list by mistake.
    with engine.connect() as connection, pytest.raises(IntegrityError, match="event_type"):
        connection.execute(
            text(
                "INSERT INTO outbox (id, user_id, event_type, payload, trace_context,"
                " occurred_at, available_at) VALUES (gen_random_uuid(), gen_random_uuid(),"
                " :event_type, '{}', '{}', now(), now())"
            ),
            {"event_type": event_type},
        )


def test_core_to_ai_list_matches_the_contract() -> None:
    # Red when: the contract gains or renames a core → ai type and the CHECK test above silently
    # stops covering the split.
    assert CORE_TO_AI < EVENT_TYPES
