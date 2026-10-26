"""T4.3: the consumer process: `python -m ai_service.messaging.consumer`."""

import io
import json
import logging
import threading
from typing import Any

import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from ai_service.handlers import HANDLERS
from ai_service.logging import configure_logging
from ai_service.messaging import consumer as consumer_module
from ai_service.messaging.consumer import Consumer, run
from tests.messaging.conftest import Names
from tests.messaging.helpers import DOCUMENT_UPLOADED, Recorder, publish, uploaded
from tests.messaging.test_consumer import make_consumer

# What core-api sends ai-service (contracts/events/README.md, "On the wire").
CORE_TO_AI = {
    "document.uploaded.v1",
    "session.confirmed.v1",
    "grade.requested.v1",
    "user.deleted.v1",
}


class FakeStop:
    """A stop event that records how long the loop asked to wait, and never really waits."""

    def __init__(self, rounds: int) -> None:
        self.rounds = rounds
        self.waits: list[float] = []

    def is_set(self) -> bool:
        return self.rounds <= 0

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(timeout or 0.0)
        return False

    def tick(self) -> None:
        self.rounds -= 1


class Scripted(Consumer):
    """A consumer whose rounds follow a script: an outcome list, or an exception to raise."""

    def __init__(self, script: list[Any], stop: FakeStop, **options: Any) -> None:
        super().__init__(**options)
        self.script = script
        self.stop = stop
        self.groups = 0
        self.group_failures = 0

    def ensure_group(self) -> None:
        self.groups += 1
        if self.groups <= self.group_failures:
            raise RedisConnectionError("Connection refused")

    def run_once(self) -> list[str]:
        self.stop.tick()
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def scripted(
    redis_client: Redis, session_factory: sessionmaker[Session], script: list[Any]
) -> tuple[Scripted, FakeStop]:
    stop = FakeStop(len(script))
    options: dict[str, Any] = {"redis": redis_client, "session_factory": session_factory}
    return Scripted(script, stop, handlers={}, **options), stop


def test_t43_run_backs_off_on_round_errors_and_recovers(
    redis_client: Redis, session_factory: sessionmaker[Session]
) -> None:
    # Review: a round that raises (Redis down, an XACK lost) must not end the process nor spin.
    down = RedisConnectionError("Connection refused")
    consumer, stop = scripted(
        redis_client, session_factory, [down, down, down, ["processed"], down]
    )
    run(consumer, stop)  # pyright: ignore[reportArgumentType]
    assert stop.waits == [1.0, 2.0, 4.0, 1.0]  # grows while failing, starts over after a success


def test_t43_run_backs_off_while_infrastructure_is_unavailable(
    redis_client: Redis, session_factory: sessionmaker[Session]
) -> None:
    # Review 🟠1: entries put back for an outage come back after min_idle; meanwhile, new ones
    # would fail the same way, so the loop slows down too.
    rounds = [["unavailable"], ["unavailable", "processed"], ["processed"], []]
    consumer, stop = scripted(redis_client, session_factory, rounds)
    run(consumer, stop)  # pyright: ignore[reportArgumentType]
    assert stop.waits == [1.0, 2.0]


def test_t43_failed_round_is_logged_without_the_exception_message(
    redis_client: Redis, session_factory: sessionmaker[Session]
) -> None:
    # ADR-0013 (finding from S2 in core-api): a database error's message holds the SQL and its
    # parameters; the round's log line must carry the class and the stack frames only.
    buffer = io.StringIO()
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, logging.getLogger("uvicorn.access").disabled)
    configure_logging("ai-consumer", "INFO", stream=buffer)
    try:
        secret = OperationalError("SELECT", {"password": "hunter2"}, Exception("password=hunter2"))
        consumer, stop = scripted(redis_client, session_factory, [secret])
        run(consumer, stop)  # pyright: ignore[reportArgumentType]
    finally:
        root.handlers, root.level, logging.getLogger("uvicorn.access").disabled = saved
    [line] = [json.loads(text) for text in buffer.getvalue().splitlines()]
    assert line["error_type"] == "OperationalError"
    assert "hunter2" not in buffer.getvalue()


def test_t43_run_backoff_is_capped(
    redis_client: Redis, session_factory: sessionmaker[Session]
) -> None:
    down = RedisConnectionError("Connection refused")
    consumer, stop = scripted(redis_client, session_factory, [down] * 10)
    run(consumer, stop)  # pyright: ignore[reportArgumentType]
    assert max(stop.waits) == consumer_module.MAX_PAUSE_S


def test_t43_run_retries_creating_the_group(
    redis_client: Redis, session_factory: sessionmaker[Session]
) -> None:
    # Review 🟢D. Red when: a Redis still starting when the consumer does ends the process, or
    # the group is created again every round.
    consumer, stop = scripted(redis_client, session_factory, [["processed"], ["processed"]])
    consumer.group_failures = 1
    run(consumer, stop)  # pyright: ignore[reportArgumentType]
    assert consumer.groups == 2
    assert stop.waits == [1.0]


def test_t43_run_handles_events_until_stopped(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    event = uploaded()
    publish(redis_client, names.stream, event)
    handled = threading.Event()

    class Signalling(Recorder):
        def __call__(self, session: Session, event: Any) -> None:
            super().__call__(session, event)
            handled.set()

    consumer = make_consumer(
        redis_client, names, session_factory, {DOCUMENT_UPLOADED: Signalling()}, block_ms=100
    )
    stop = threading.Event()
    thread = threading.Thread(target=run, args=(consumer, stop))
    thread.start()
    try:
        assert handled.wait(5)
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive()


def test_t43_main_without_redis_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # Review 🟢12: fail closed rather than run without a queue.
    monkeypatch.delenv("AI_REDIS_URL", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        consumer_module.main()
    assert exit_info.value.code not in (0, None)


def test_t43_handlers_only_for_events_core_sends() -> None:
    # T4.7 fills the registry; a handler for an event ai-service itself sends would never run.
    assert set(HANDLERS) <= CORE_TO_AI
