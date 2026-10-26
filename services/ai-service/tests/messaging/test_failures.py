"""T4.3: what the consumer does with an event it cannot handle: retry with backoff, then the
dead letter; at once for an event that can never succeed (poison, unknown, another user's keys).
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from redis import Redis
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from ai_service.messaging.consumer import backoff_ms, keys_belong_to_user
from ai_service.messaging.envelope import parse_event
from ai_service.messaging.idempotency import claim
from tests.messaging.conftest import Names
from tests.messaging.helpers import (
    DOCUMENT_UPLOADED,
    SECRET_DETAIL,
    Recorder,
    boom,
    publish,
    uploaded,
)
from tests.messaging.test_consumer import make_consumer, pending

EXAMPLES = Path(__file__).resolve().parents[4] / "contracts" / "events" / "examples"
VALID_EXAMPLES = sorted(p for p in EXAMPLES.glob("*.json") if ".invalid-" not in p.name)


def dead_entries(redis: Redis, names: Names) -> list[dict[str, str]]:
    entries: list[tuple[str, dict[str, str]]] = redis.xrange(names.dead)  # pyright: ignore[reportAssignmentType]
    return [fields for _, fields in entries]


def example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def test_t43_handler_fails_over_limit_goes_to_dead_letter(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Xong khi 2. Red when: the limit is off by one either way, or the entry stays pending.
    event = uploaded()
    entry_id = publish(redis_client, names.stream, event)
    recorder = Recorder(fail_with=boom)
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    for _ in range(4):
        assert consumer.run_once() == ["retry"]
    assert dead_entries(redis_client, names) == []
    assert consumer.run_once() == ["dead"]
    assert len(recorder.calls) == 5
    assert pending(redis_client, names) == 0
    [dead] = dead_entries(redis_client, names)
    # Plan Y2: the original envelope, where it came from, why, how often. Never the message.
    assert dead == {
        "envelope": json.dumps(event),
        "stream": names.stream,
        "entry_id": entry_id,
        "reason": "Boom",
        "deliveries": "5",
    }
    assert SECRET_DETAIL not in json.dumps(dead, ensure_ascii=False)


def test_t43_backoff_grows_and_stops_at_min_idle() -> None:
    assert [backoff_ms(n, base_ms=5_000, cap_ms=60_000) for n in range(1, 6)] == [
        5_000,
        15_000,
        45_000,
        60_000,
        60_000,
    ]


def test_t43_failed_entry_is_not_reclaimed_before_its_backoff(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: a failed entry waits the full min_idle (no backoff) or comes back at once.
    publish(redis_client, names.stream, uploaded())
    recorder = Recorder(fail_with=boom)
    consumer = make_consumer(
        redis_client,
        names,
        session_factory,
        {DOCUMENT_UPLOADED: recorder},
        min_idle_ms=60_000,
        backoff_base_ms=5_000,
    )
    consumer.ensure_group()
    assert consumer.run_once() == ["retry"]
    [row] = redis_client.xpending_range(names.stream, names.group, "-", "+", 1)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    # Counted as idle for min_idle - backoff already: due again in 5 s, not in 60 s.
    assert 55_000 <= int(row["time_since_delivered"]) < 60_000  # pyright: ignore[reportUnknownArgumentType]
    assert int(row["times_delivered"]) == 1  # pyright: ignore[reportUnknownArgumentType]
    assert consumer.run_once() == []


def test_t43_backoff_longer_than_min_idle_is_clamped(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Review 🟡9: a negative IDLE is an error in Redis; the entry is simply due at once.
    publish(redis_client, names.stream, uploaded())
    recorder = Recorder(fail_with=boom)
    consumer = make_consumer(
        redis_client,
        names,
        session_factory,
        {DOCUMENT_UPLOADED: recorder},
        min_idle_ms=100,
        backoff_base_ms=5_000,
    )
    consumer.ensure_group()
    assert consumer.run_once() == ["retry"]


@pytest.mark.parametrize(
    "fields",
    [
        {"envelope": "not json"},
        {"envelope": "{}"},
        {"envelope": json.dumps({**uploaded(), "user_id": None})},
        {"envelope": json.dumps({**uploaded(), "extra": 1})},
        {"something": "else"},
    ],
    ids=["not-json", "empty-object", "null-user", "extra-field", "no-envelope-field"],
)
def test_t43_poison_envelope_goes_to_dead_letter_without_retry(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    fields: dict[str, str],
) -> None:
    # Red when: an entry that can never parse is retried, and blocks five rounds for nothing.
    entry_id = str(redis_client.xadd(names.stream, fields))  # pyright: ignore[reportArgumentType]
    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    assert consumer.run_once() == ["dead"]
    assert recorder.calls == []
    assert pending(redis_client, names) == 0
    [dead] = dead_entries(redis_client, names)
    assert dead["reason"] == "invalid_envelope"
    assert dead["entry_id"] == entry_id
    assert dead["envelope"] == fields.get("envelope", "")
    assert dead["deliveries"] == "1"


def test_t43_entry_that_is_not_utf8_goes_to_dead_letter(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Review 🟡A. Red when: the client decodes strictly, XAUTOCLAIM raises on the entry every
    # round, and nothing after it is ever handled.
    redis_client.xadd(names.stream, {"envelope": b"\xff\xfe"})
    publish(redis_client, names.stream, uploaded())
    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    redis_client.xreadgroup(names.group, "crashed-consumer", {names.stream: ">"}, count=1)
    assert consumer.run_once() == ["dead", "processed"]
    assert [d["reason"] for d in dead_entries(redis_client, names)] == ["invalid_envelope"]
    assert len(recorder.calls) == 1


def test_t43_unknown_event_type_dead_lettered(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    publish(redis_client, names.stream, {**uploaded(), "event_type": "document.shredded.v1"})
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    assert consumer.run_once() == ["dead"]
    assert [d["reason"] for d in dead_entries(redis_client, names)] == ["unknown_type"]


def test_t43_known_type_without_handler_dead_lettered(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # A contract event with no handler yet (T4.7 adds them): kept for a replay, not dropped.
    publish(redis_client, names.stream, example("grade.requested.v1"))
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    assert consumer.run_once() == ["dead"]
    assert [d["reason"] for d in dead_entries(redis_client, names)] == ["no_handler"]


def test_t43_foreign_user_object_key_goes_to_dead_letter_without_calling_handler(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # F2. Red when: the key is not checked, and user A's event makes ai-service read B's file.
    publish(redis_client, names.stream, uploaded(key_owner=uuid.uuid4()))
    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    assert consumer.run_once() == ["dead"]
    assert recorder.calls == []
    assert [d["reason"] for d in dead_entries(redis_client, names)] == ["user_mismatch"]


def test_t43_foreign_key_inside_a_list_is_caught() -> None:
    # Review 🟡8: note_image_keys is a list of keys.
    event = example("session.confirmed.v1")
    other = str(uuid.uuid4())
    event["payload"]["note_image_keys"].append(f"users/{other}/subjects/x/notes/y/2.jpg")
    assert keys_belong_to_user(parse_event(json.dumps(event))) is False


@pytest.mark.parametrize("path", VALID_EXAMPLES, ids=lambda p: p.stem)
def test_t43_every_object_key_in_every_example_is_checked(path: Path) -> None:
    # Review 🟡8: the check goes by type, through lists and nested models. Every key in every
    # contract example is moved to another user in turn, and each move must be caught; a new
    # event with a key the check cannot see turns this red.
    text = path.read_text(encoding="utf-8")
    event = parse_event(text)
    assert keys_belong_to_user(event) is True
    owner = f"users/{event.user_id}/"
    other = f"users/{uuid.uuid4()}/"
    count = text.count(owner)
    for index in range(count):
        head, *tail = text.split(owner)
        moved = owner.join([head, *tail[:index]]) + other + owner.join(tail[index:])
        assert moved.count(owner) == count - 1
        assert keys_belong_to_user(parse_event(moved)) is False, (path.name, index)


def test_t43_entry_delivered_more_than_max_without_result_goes_dead_without_handler(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # An entry that crashed the consumer each time (no failure recorded): it must not loop.
    entry_id = publish(redis_client, names.stream, uploaded())
    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    redis_client.xreadgroup(names.group, "crashed-consumer", {names.stream: ">"}, count=1)
    redis_client.xclaim(names.stream, names.group, "crashed-consumer", 0, [entry_id], retrycount=5)
    assert consumer.run_once() == ["dead"]  # delivered a sixth time
    assert recorder.calls == []
    [dead] = dead_entries(redis_client, names)
    assert (dead["reason"], dead["deliveries"]) == ("max_deliveries", "6")


def test_t43_entry_delivered_too_often_and_unreadable_record_goes_dead(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Review 🟢F. Red when: a database error that is not an outage (a schema out of step) is
    # raised out of the round, and the entry fails every round after min_idle for ever.
    entry_id = publish(redis_client, names.stream, uploaded())
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    redis_client.xreadgroup(names.group, "crashed-consumer", {names.stream: ">"}, count=1)
    redis_client.xclaim(names.stream, names.group, "crashed-consumer", 0, [entry_id], retrycount=5)

    def broken_sessions() -> Session:
        raise ProgrammingError("SELECT", {}, Exception('relation "processed_event" is missing'))

    consumer.session_factory = broken_sessions
    assert consumer.run_once() == ["dead"]
    [dead] = dead_entries(redis_client, names)
    assert dead["reason"] == "max_deliveries"


def test_t43_entry_delivered_too_often_but_already_handled_is_acked(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Review 🟡4: committed, then the ack was lost again and again: not a dead letter.
    event = uploaded()
    entry_id = publish(redis_client, names.stream, event)
    with session_factory() as session, session.begin():
        claim(session, names.group, uuid.UUID(event["event_id"]))
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    redis_client.xreadgroup(names.group, "crashed-consumer", {names.stream: ">"}, count=1)
    redis_client.xclaim(names.stream, names.group, "crashed-consumer", 0, [entry_id], retrycount=5)
    assert consumer.run_once() == ["duplicate"]
    assert dead_entries(redis_client, names) == []
    assert pending(redis_client, names) == 0
