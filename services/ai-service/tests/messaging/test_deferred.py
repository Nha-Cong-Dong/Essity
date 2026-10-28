"""T4.3: a deferred task goes back to the queue and is not a failure (PLAN T4.3 "Xong khi" 3).

Quotas themselves are T2.11 (postponed): here a handler raises `Deferred` on its own. An
infrastructure outage (database or Redis connection) is handled the same way (review 🟠1),
so a few minutes of downtime do not send every event to the dead letter.
"""

from collections.abc import Callable

import psycopg.errors
import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from ai_service.messaging.consumer import Deferred
from tests.messaging.conftest import Names
from tests.messaging.helpers import DOCUMENT_UPLOADED, Recorder, boom, publish, uploaded
from tests.messaging.test_consumer import claimed, make_consumer, pending
from tests.messaging.test_failures import dead_entries


def times_delivered(redis: Redis, names: Names) -> int:
    [row] = redis.xpending_range(names.stream, names.group, "-", "+", 1)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    return int(row["times_delivered"])  # pyright: ignore[reportUnknownArgumentType]


def test_t43_deferred_task_never_dead_lettered(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Xong khi 3. Red when: a deferral counts as a delivery, and a user over quota for a day
    # loses their document to the dead letter after five tries.
    event = uploaded()
    publish(redis_client, names.stream, event)
    recorder = Recorder(fail_with=Deferred)
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    for _ in range(7):
        assert consumer.run_once() == ["deferred"]
        assert times_delivered(redis_client, names) <= 1
    assert len(recorder.calls) == 7
    assert dead_entries(redis_client, names) == []
    assert pending(redis_client, names) == 1
    assert not claimed(session_factory, names.group, event["event_id"])


def test_t43_deferred_then_succeeds_runs_once_and_acks(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    event = uploaded()
    publish(redis_client, names.stream, event)
    recorder = Recorder(fail_with=Deferred)
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    assert consumer.run_once() == ["deferred"]
    assert consumer.run_once() == ["deferred"]
    recorder.fail_with = None
    assert consumer.run_once() == ["processed"]
    assert pending(redis_client, names) == 0
    assert claimed(session_factory, names.group, event["event_id"])
    assert consumer.run_once() == []


def test_t43_defer_then_real_errors_count_from_zero(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: deferrals are added to real failures, and the dead letter comes early.
    publish(redis_client, names.stream, uploaded())
    recorder = Recorder(fail_with=Deferred)
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    for _ in range(3):
        assert consumer.run_once() == ["deferred"]
    recorder.fail_with = boom
    for _ in range(4):
        assert consumer.run_once() == ["retry"]
    assert dead_entries(redis_client, names) == []
    assert consumer.run_once() == ["dead"]
    [dead] = dead_entries(redis_client, names)
    assert (dead["reason"], dead["deliveries"]) == ("Boom", "5")


def test_t43_deferred_entry_waits_min_idle_before_coming_back(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: a deferred entry comes straight back, and the consumer spins on it.
    publish(redis_client, names.stream, uploaded())
    recorder = Recorder(fail_with=Deferred)
    consumer = make_consumer(
        redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder}, min_idle_ms=60_000
    )
    consumer.ensure_group()
    assert consumer.run_once() == ["deferred"]
    assert consumer.run_once() == []
    assert len(recorder.calls) == 1


def operational() -> Exception:
    return OperationalError("SELECT 1", {}, Exception("server closed the connection"))


def interface() -> Exception:
    return InterfaceError("SELECT 1", {}, Exception("connection already closed"))


def redis_down() -> Exception:
    return RedisConnectionError("Connection refused")


def server_closed() -> Exception:
    return OperationalError("SELECT 1", {}, psycopg.errors.AdminShutdown())


def connection_lost() -> Exception:
    return OperationalError("SELECT 1", {}, psycopg.errors.ConnectionFailure())


@pytest.mark.parametrize(
    "error",
    [
        psycopg.errors.QueryCanceled,
        psycopg.errors.DeadlockDetected,
        psycopg.errors.ProgramLimitExceeded,
    ],
)
def test_t43_operational_error_from_the_query_counts_as_a_failure(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    error: type[Exception],
) -> None:
    # Review 🟠C. Red when: every OperationalError is an outage, and a statement that always
    # times out is retried every minute for ever, paying for the LLM call each time.
    publish(redis_client, names.stream, uploaded())
    recorder = Recorder(fail_with=lambda: OperationalError("INSERT", {}, error()))
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    for _ in range(4):
        assert consumer.run_once() == ["retry"]
    assert consumer.run_once() == ["dead"]
    [dead] = dead_entries(redis_client, names)
    assert dead["reason"] == "OperationalError"


@pytest.mark.parametrize(
    "outage", [operational, interface, redis_down, server_closed, connection_lost]
)
def test_t43_db_outage_does_not_burn_attempts(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    outage: Callable[[], Exception],
) -> None:
    # Review 🟠1. Red when: an outage counts as the handler failing, and Postgres restarting
    # for two minutes sends every event in flight to the dead letter.
    publish(redis_client, names.stream, uploaded())
    recorder = Recorder(fail_with=outage)
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    for _ in range(6):
        assert consumer.run_once() == ["unavailable"]
        assert times_delivered(redis_client, names) <= 1
    assert dead_entries(redis_client, names) == []
    recorder.fail_with = None
    assert consumer.run_once() == ["processed"]
    assert pending(redis_client, names) == 0
