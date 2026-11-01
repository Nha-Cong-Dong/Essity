"""T7.8b tester edges of `unit.saved.v1` in ai-service: a malformed one still reaches the dead
letter (removing SKIPPED_TYPES must not turn into "drop anything named unit.saved"), the handler
refuses another event type, and its log line holds ids only (ADR-0013)."""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import pytest
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ai_service.messaging.envelope import parse_event
from ai_service.tasks.unit_saved import OnUnitSaved
from tests.messaging.conftest import Names
from tests.messaging.helpers import publish, uploaded
from tests.messaging.test_consumer import make_consumer, pending

EXAMPLES = Path(__file__).resolve().parents[4] / "contracts" / "events" / "examples"


def unit_saved(user: uuid.UUID, **payload: Any) -> dict[str, Any]:
    body = {"unit_id": str(uuid.uuid4()), "unit_rev": 1, "subject_id": str(uuid.uuid4())}
    return {**uploaded(user), "event_type": "unit.saved.v1", "payload": body | payload}


def dead_reasons(redis: Redis, names: Names) -> list[str]:
    entries: list[tuple[str, dict[str, str]]] = redis.xrange(names.dead)  # pyright: ignore[reportAssignmentType]
    return [fields["reason"] for _, fields in entries]


@pytest.mark.parametrize(
    "payload",
    [{"unit_rev": 0}, {"title": "Thẻ 1"}, {"subject_id": None}],
    ids=["rev-zero", "carries-title", "no-subject"],
)
def test_t78b_a_malformed_unit_saved_goes_to_dead_letter_not_to_the_handler(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    payload: dict[str, Any],
) -> None:
    # Red when: the consumer acks any unit.saved.v1 (the old SKIPPED_TYPES path coming back), or
    # the model accepts rev 0, an extra field (a card title leaking) or no subject.
    calls: list[Any] = []

    class Spy(OnUnitSaved):
        def __call__(self, session: Session, event: Any) -> None:
            calls.append(event)

    publish(redis_client, names.stream, unit_saved(uuid.uuid4(), **payload))
    consumer = make_consumer(redis_client, names, session_factory, {"unit.saved.v1": Spy()})
    consumer.ensure_group()
    assert consumer.run_once() == ["dead"]
    assert calls == []
    assert dead_reasons(redis_client, names) == ["invalid_envelope"]
    assert pending(redis_client, names) == 0


def test_t78b_the_contract_example_is_handled_once(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: the contract example of unit.saved.v1 does not parse in ai-service.
    event = json.loads((EXAMPLES / "unit.saved.v1.json").read_text(encoding="utf-8"))
    publish(redis_client, names.stream, event)
    consumer = make_consumer(redis_client, names, session_factory, {"unit.saved.v1": OnUnitSaved()})
    consumer.ensure_group()
    assert consumer.run_once() == ["processed"]
    assert dead_reasons(redis_client, names) == []


def test_t78b_handler_refuses_another_event_type() -> None:
    # Red when: OnUnitSaved accepts any event and is wired under a wrong type without noticing.
    other = parse_event(json.dumps(uploaded(uuid.uuid4())))
    with pytest.raises(TypeError):
        OnUnitSaved()(None, other)  # pyright: ignore[reportArgumentType]


def test_t78b_handler_logs_ids_only(caplog: pytest.LogCaptureFixture) -> None:
    # Red when: the log line drops the ids it is for, or gains a card field (ADR-0013).
    body = unit_saved(uuid.uuid4())
    event = parse_event(json.dumps(body))
    with caplog.at_level(logging.INFO, logger="ai_service.tasks"):
        OnUnitSaved()(None, event)  # pyright: ignore[reportArgumentType]
    [record] = [r for r in caplog.records if r.name == "ai_service.tasks"]
    assert record.getMessage() == "unit saved received"
    assert record.__dict__["unit_rev"] == 1
    assert record.__dict__["unit_id"] == body["payload"]["unit_id"]
    assert "subject_id" not in record.__dict__ and "title" not in record.__dict__
