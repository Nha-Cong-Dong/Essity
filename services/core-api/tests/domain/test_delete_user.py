"""T6.3: erase everything of one user. Real PostgreSQL (three logins), Redis and a storage double.

Every test builds two users and checks that B is whole after A is erased: a wrong `user_id`
filter anywhere is the failure this task must not have.
"""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from redis import Redis
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.clients.storage import StorageUnavailableError
from core_api.domain import delete_user as module
from core_api.domain.delete_user import (
    ERASE_USER_SWEEP,
    SWEEP_DELAY,
    EraseRefused,
    erase_user,
    scrub_stream,
    sweep_user,
)
from core_api.messaging.envelope import GradeRequested
from core_api.messaging.outbox import enqueue_event
from core_api.messaging.relay import envelope_of
from erase_world import World, build_world, rows_of, tables_with_user_id
from erasure import erase_user as erase_rows
from fake_storage import FakeStorage

NOW = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
Entries = list[tuple[bytes, dict[bytes, bytes]]]


class Streams:
    """Redis names of this test's own: the test Redis is shared and never flushed."""

    def __init__(self, redis: Redis) -> None:
        tag = uuid.uuid4()
        self.redis = redis
        self.core = f"test.events.core.{tag}"
        self.ai = f"test.events.ai.{tag}"
        self.dead = f"test.events.dead.{tag}"

    @property
    def names(self) -> tuple[str, str]:
        return (self.core, self.ai)

    def add(self, stream: str, user: uuid.UUID, event_type: str = "session.confirmed.v1") -> None:
        envelope = json.dumps(
            {"event_type": event_type, "user_id": str(user), "payload": {"notes": "ghi chú"}}
        )
        self.redis.xadd(stream, {"envelope": envelope})

    def users_in(self, stream: str) -> list[tuple[str, str | None]]:
        entries = cast(Entries, self.redis.xrange(stream))
        parsed = [json.loads(fields[b"envelope"]) for _, fields in entries]
        return [(item["user_id"], item.get("event_type")) for item in parsed]


@pytest.fixture
def streams(redis_client: Redis) -> Iterator[Streams]:
    made = Streams(redis_client)
    yield made
    redis_client.delete(made.core, made.ai, made.dead)


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


def _tidy(engine: Engine, eraser_engine: Engine, *users: uuid.UUID) -> None:
    for user in users:
        erase_rows(eraser_engine, user)
    with engine.begin() as connection:
        for user in users:
            connection.execute(text("DELETE FROM outbox WHERE user_id = :u"), {"u": user})
            connection.execute(
                text("DELETE FROM procrastinate_jobs WHERE args->'payload'->>'user_id' = :u"),
                {"u": str(user)},
            )


@pytest.fixture
def a(engine: Engine, eraser_engine: Engine) -> Iterator[World]:
    world = build_world(engine)
    yield world
    _tidy(engine, eraser_engine, world.user_id)


@pytest.fixture
def b(engine: Engine, eraser_engine: Engine) -> Iterator[World]:
    world = build_world(engine)
    yield world
    _tidy(engine, eraser_engine, world.user_id)


def email_of(engine: Engine, user: uuid.UUID) -> str:
    with engine.connect() as connection:
        return str(connection.scalar(text('SELECT email FROM "user" WHERE id = :u'), {"u": user}))


def queue_event(engine: Engine, user: uuid.UUID, *, sent: bool = False) -> None:
    """A grade.requested.v1 of `user` in the outbox, as a request would have left it."""
    with Session(engine) as session:
        enqueue_event(
            session,
            GradeRequested(
                attempt_id=uuid.uuid4(),
                request_key=f"users/{user}/grading/{uuid.uuid4()}/request.json",
            ),
            user_id=user,
            now=NOW,
        )
        if sent:
            session.flush()
            session.execute(
                text("UPDATE outbox SET sent_at = now() WHERE user_id = :u"), {"u": user}
            )
        session.commit()


def outbox_types(engine: Engine, user: uuid.UUID) -> list[str]:
    with engine.connect() as connection:
        return sorted(
            connection.scalars(
                text("SELECT event_type FROM outbox WHERE user_id = :u"), {"u": user}
            )
        )


def jobs_of(engine: Engine, user: uuid.UUID) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT task_name, scheduled_at FROM procrastinate_jobs"
                    " WHERE args->'payload'->>'user_id' = :u"
                ),
                {"u": str(user)},
            )
        )


def objects_for(storage: FakeStorage, user: uuid.UUID) -> None:
    for tail in ("raw/a.pdf", "derived/vision/p1.json", "derived/submission/s1.json", "x/y/z"):
        storage.put(f"users/{user}/{tail}", b"data", None)


def erase(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    streams: Streams,
    user: uuid.UUID,
    email: str | None,
) -> module.EraseResult:
    return erase_user(
        eraser_engine=eraser_engine,
        app_engine=engine,
        storage=storage,
        redis=streams.redis,
        user_id=user,
        now=NOW,
        confirm_email=email,
        dead_stream=streams.dead,
        streams=streams.names,
    )


def test_t63_erase_a_keeps_b_whole(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    streams: Streams,
    a: World,
    b: World,
) -> None:
    # Red when: any delete misses the user_id filter, in a table, the outbox, the store or Redis.
    for user in (a.user_id, b.user_id):
        queue_event(engine, user)
        queue_event(engine, user, sent=True)
        objects_for(storage, user)
        streams.add(streams.core, user)
        streams.add(streams.ai, user)
        streams.redis.xadd(streams.dead, {"envelope": json.dumps({"user_id": str(user)})})
    before_b = rows_of(engine, b.user_id)
    b_objects = {key for key in storage.objects if str(b.user_id) in key}

    result = erase(engine, eraser_engine, storage, streams, a.user_id, email_of(engine, a.user_id))

    assert result.user_existed
    left = {table: n for table, n in rows_of(engine, a.user_id).items() if n}
    assert left == {"outbox": 1}  # only the user.deleted.v1 that must outlive the user
    assert rows_of(engine, b.user_id) == before_b
    assert outbox_types(engine, b.user_id) == ["grade.requested.v1", "grade.requested.v1"]
    assert {key for key in storage.objects if str(b.user_id) in key} == b_objects
    assert not any(str(a.user_id) in key for key in storage.objects)
    assert streams.users_in(streams.core) == [(str(b.user_id), "session.confirmed.v1")]
    assert streams.users_in(streams.ai) == [(str(b.user_id), "session.confirmed.v1")]
    assert streams.users_in(streams.dead) == [(str(b.user_id), None)]


def test_t63_every_table_with_a_user_id_is_cascaded_except_the_outbox(engine: Engine) -> None:
    # Red when: a table gets a `user_id` without a cascading foreign key to "user" (its rows
    # would outlive the user) and nobody teaches this task about it.
    with engine.connect() as connection:
        cascaded = set(
            connection.scalars(
                text(
                    "SELECT DISTINCT c.conrelid::regclass::text FROM pg_constraint c"
                    " JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)"
                    " WHERE c.contype = 'f' AND c.confrelid = '\"user\"'::regclass"
                    " AND c.confdeltype = 'c' AND a.attname = 'user_id'"
                )
            )
        )
    assert set(tables_with_user_id(engine)) - cascaded == {"outbox"}


def test_t63_outbox_keeps_only_user_deleted_and_it_is_a_valid_event(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    streams: Streams,
    a: World,
) -> None:
    # Red when: an unsent event of the erased user stays (it would reach ai-service), the
    # user.deleted.v1 is deleted with its user, or its payload breaks the contract.
    queue_event(engine, a.user_id)  # unsent
    queue_event(engine, a.user_id, sent=True)

    erase(engine, eraser_engine, storage, streams, a.user_id, email_of(engine, a.user_id))

    assert outbox_types(engine, a.user_id) == ["user.deleted.v1"]
    with Session(engine) as session:
        row = session.execute(
            text("SELECT * FROM outbox WHERE user_id = :u"), {"u": a.user_id}
        ).one()
        assert row.payload == {} and row.sent_at is None
        from core_api.db.models import Outbox

        outbox = session.get(Outbox, row.id)
        assert outbox is not None
        assert json.loads(envelope_of(outbox))["event_type"] == "user.deleted.v1"


def test_t63_the_sweep_job_is_queued_with_the_event_in_one_transaction(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    streams: Streams,
    a: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: the sweep is not scheduled, is scheduled sooner than SWEEP_DELAY, or is queued
    # outside the transaction of the event (a failure between them leaves one without the other).
    email = email_of(engine, a.user_id)
    boom = RuntimeError("queue down")

    def broken(*args: object, **kwargs: object) -> bool:
        raise boom

    monkeypatch.setattr(module, "enqueue_job", broken)
    with pytest.raises(RuntimeError):
        erase(engine, eraser_engine, storage, streams, a.user_id, email)
    assert "user.deleted.v1" not in outbox_types(engine, a.user_id)
    assert jobs_of(engine, a.user_id) == []
    monkeypatch.undo()

    erase(engine, eraser_engine, storage, streams, a.user_id, None)  # user is gone: no email

    (job,) = jobs_of(engine, a.user_id)
    assert job.task_name == ERASE_USER_SWEEP
    delay = job.scheduled_at - datetime.now(UTC)
    assert (
        timedelta(minutes=SWEEP_DELAY["minutes"] - 2)
        < delay
        <= timedelta(minutes=SWEEP_DELAY["minutes"])
    )


def test_t63_erase_twice_and_for_an_unknown_user_is_safe(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    streams: Streams,
    a: World,
    b: World,
) -> None:
    # Red when: the second run raises, deletes something of B, or the unknown id needs an email.
    email = email_of(engine, a.user_id)
    erase(engine, eraser_engine, storage, streams, a.user_id, email)
    before_b = rows_of(engine, b.user_id)

    again = erase(engine, eraser_engine, storage, streams, a.user_id, None)
    stranger = uuid.uuid4()
    erase(engine, eraser_engine, storage, streams, stranger, None)

    assert not again.user_existed
    assert outbox_types(engine, a.user_id) == ["user.deleted.v1", "user.deleted.v1"]
    assert rows_of(engine, b.user_id) == before_b
    _tidy(engine, eraser_engine, stranger)


def test_t63_a_storage_failure_stops_the_command_and_a_rerun_finishes(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    streams: Streams,
    a: World,
) -> None:
    # Red when: a half-done erase cannot be completed, or the failure is reported as success.
    objects_for(storage, a.user_id)
    streams.add(streams.core, a.user_id)
    email = email_of(engine, a.user_id)
    storage.delete_fails = True
    with pytest.raises(StorageUnavailableError):
        erase(engine, eraser_engine, storage, streams, a.user_id, email)
    assert rows_of(engine, a.user_id)["user"] == 0  # the row went: cleanup is for the rerun
    assert storage.objects

    storage.delete_fails = False
    erase(engine, eraser_engine, storage, streams, a.user_id, None)

    assert not storage.objects
    assert streams.users_in(streams.core) == []


@pytest.mark.parametrize("email", [None, "someone-else@example.com"])
def test_t63_a_living_user_needs_their_exact_email(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    streams: Streams,
    a: World,
    email: str | None,
) -> None:
    # Red when: a mistyped id erases a real person: nothing may change without the email.
    objects_for(storage, a.user_id)
    before = rows_of(engine, a.user_id)
    with pytest.raises(EraseRefused):
        erase(engine, eraser_engine, storage, streams, a.user_id, email)
    assert rows_of(engine, a.user_id) == before
    assert storage.objects
    assert outbox_types(engine, a.user_id) == []

    erase(
        engine,
        eraser_engine,
        storage,
        streams,
        a.user_id,
        email_of(engine, a.user_id).upper(),  # case does not matter
    )
    assert rows_of(engine, a.user_id)["user"] == 0


def test_t63_the_app_login_is_refused_as_the_eraser(
    engine: Engine, storage: FakeStorage, streams: Streams, a: World
) -> None:
    # Red when: the command runs with a login that is not a core_eraser member, where the
    # history triggers would refuse it half way (or let an owner login do anything).
    objects_for(storage, a.user_id)
    with pytest.raises(EraseRefused):
        erase(engine, engine, storage, streams, a.user_id, email_of(engine, a.user_id))
    assert rows_of(engine, a.user_id)["user"] == 1
    assert storage.objects


def test_t63_nothing_outside_the_database_is_touched_while_the_user_still_exists(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    streams: Streams,
    a: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: an eraser pointed at the wrong database (it deletes 0 rows there) goes on to
    # delete the files and the events of a user who is alive in the app's database (review O3).
    objects_for(storage, a.user_id)
    streams.add(streams.core, a.user_id)

    def missed(*args: object) -> bool:
        return False

    monkeypatch.setattr(module, "_delete_user_row", missed)

    with pytest.raises(EraseRefused):
        erase(engine, eraser_engine, storage, streams, a.user_id, None)

    assert storage.objects and not storage.deleted
    assert streams.users_in(streams.core) != []
    assert outbox_types(engine, a.user_id) == []
    assert jobs_of(engine, a.user_id) == []
    with pytest.raises(EraseRefused):
        sweep_user(
            app_engine=engine,
            storage=storage,
            redis=streams.redis,
            user_id=a.user_id,
            now=NOW,
            dead_stream=streams.dead,
            streams=streams.names,
        )
    assert storage.objects


def test_t63_the_sweep_removes_what_was_written_after_the_erase(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    streams: Streams,
    a: World,
    b: World,
) -> None:
    # Red when: a task in flight when the erase ran leaves a trace for good (an outbox row, an
    # object under derived/, a dead letter or an event with the user's notes).
    erase(engine, eraser_engine, storage, streams, a.user_id, email_of(engine, a.user_id))
    queue_event(engine, a.user_id)  # a request that had read the user before it went
    queue_event(engine, b.user_id)
    storage.put(f"users/{a.user_id}/derived/vision/late.json", b"x", None)
    storage.put(f"users/{b.user_id}/derived/vision/mine.json", b"x", None)
    streams.add(streams.ai, a.user_id)  # an answer of ai-service about A, delivered late
    streams.add(streams.ai, b.user_id)
    streams.add(streams.core, a.user_id, "user.deleted.v1")  # an order not yet delivered
    streams.redis.xadd(streams.dead, {"envelope": json.dumps({"user_id": str(a.user_id)})})

    sweep_user(
        app_engine=engine,
        storage=storage,
        redis=streams.redis,
        user_id=a.user_id,
        now=NOW,
        dead_stream=streams.dead,
        streams=streams.names,
    )

    assert outbox_types(engine, a.user_id) == ["user.deleted.v1", "user.deleted.v1"]
    assert list(storage.objects) == [f"users/{b.user_id}/derived/vision/mine.json"]
    assert streams.users_in(streams.ai) == [(str(b.user_id), "session.confirmed.v1")]
    assert streams.users_in(streams.core) == [(str(a.user_id), "user.deleted.v1")]
    assert streams.users_in(streams.dead) == []
    assert outbox_types(engine, b.user_id) == ["grade.requested.v1"]
    assert len(jobs_of(engine, a.user_id)) == 1  # the sweep does not queue itself again


def test_t63_scrub_reads_a_long_stream_in_batches(streams: Streams) -> None:
    # Red when: the scan stops after the first batch, skips the entry at a batch edge, or
    # removes an entry of another user or the user.deleted.v1 of the same one.
    mine, other = uuid.uuid4(), uuid.uuid4()
    for index in range(1203):
        streams.add(streams.core, mine if index % 3 == 0 else other)
    streams.add(streams.core, mine, "user.deleted.v1")

    removed = scrub_stream(streams.redis, streams.core, mine)

    assert removed == 401
    left = streams.users_in(streams.core)
    assert [pair for pair in left if pair[0] == str(mine)] == [(str(mine), "user.deleted.v1")]
    assert len(left) == 802 + 1


def test_t63_the_job_runs_the_sweep(
    engine: Engine,
    eraser_engine: Engine,
    storage: FakeStorage,
    redis_client: Redis,
    a: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: the job kind is not registered or its handler reads the user from anywhere but
    # its payload.
    from core_api.jobs import erase_user_sweep as job

    erase_rows(eraser_engine, a.user_id)
    storage.put(f"users/{a.user_id}/derived/vision/late.json", b"x", None)
    queue_event(engine, a.user_id)
    monkeypatch.setattr(job, "_storage", lambda: storage)

    job.erase_user_sweep({"user_id": str(a.user_id)})

    assert not storage.objects
    assert outbox_types(engine, a.user_id) == ["user.deleted.v1"]


def test_t63_the_job_refuses_a_user_that_exists(
    storage: FakeStorage, a: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: a stale job deletes the files of a user who is alive.
    from core_api.jobs import erase_user_sweep as job

    objects_for(storage, a.user_id)
    monkeypatch.setattr(job, "_storage", lambda: storage)
    with pytest.raises(EraseRefused):
        job.erase_user_sweep({"user_id": str(a.user_id)})
    assert storage.objects
