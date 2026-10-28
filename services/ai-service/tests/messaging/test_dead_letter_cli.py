"""T4.3: `python -m ai_service.messaging.dead_letter`: list, replay and purge the dead letter.

`events.dead` is shared with core-api: this tool only lists and replays entries that came from
`events.core`. Purging a user's entries (review 🟠2, for T6.3) covers both directions.
"""

import json
import uuid

import pytest
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ai_service.messaging import dead_letter
from ai_service.messaging.dead_letter import list_entries, purge_user, replay
from tests.conftest import TEST_REDIS_URL
from tests.messaging.conftest import Names
from tests.messaging.helpers import DOCUMENT_UPLOADED, Recorder, publish, uploaded
from tests.messaging.test_consumer import make_consumer, pending
from tests.messaging.test_failures import dead_entries


def dead_from_core(
    redis: Redis, names: Names, session_factory: sessionmaker[Session], event: dict[str, object]
) -> None:
    """Send `event` through the consumer with no handler: it lands in the dead letter."""
    publish(redis, names.stream, event)
    consumer = make_consumer(redis, names, session_factory, {})
    consumer.ensure_group()
    assert consumer.run_once() == ["dead"]


def add_dead(redis: Redis, names: Names, *, stream: str, envelope: str) -> str:
    fields = {
        "envelope": envelope,
        "stream": stream,
        "entry_id": "1-0",
        "reason": "x",
        "deliveries": 1,
    }
    return str(redis.xadd(names.dead, fields))  # pyright: ignore[reportArgumentType]


def test_t43_replay_moves_only_this_streams_entries_back_and_handler_runs(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: replay also moves core-api's entries (events.ai) into events.core, or an entry
    # without an envelope (review 🟡7).
    event = uploaded()
    dead_from_core(redis_client, names, session_factory, event)
    add_dead(redis_client, names, stream="events.ai", envelope=json.dumps(uploaded()))
    add_dead(redis_client, names, stream=names.stream, envelope="")
    assert replay(redis_client, dead_stream=names.dead, stream=names.stream) == 1
    left = dead_entries(redis_client, names)
    assert sorted(d["stream"] for d in left) == sorted(["events.ai", names.stream])
    assert all(d["envelope"] != json.dumps(event) for d in left)
    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    assert consumer.run_once() == ["processed"]
    assert [str(e.event_id) for e in recorder.calls] == [event["event_id"]]
    assert pending(redis_client, names) == 0


def test_t43_replay_by_id_moves_that_entry_only(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    first, second = uploaded(), uploaded()
    dead_from_core(redis_client, names, session_factory, first)
    dead_from_core(redis_client, names, session_factory, second)
    first_dead_id = list_entries(redis_client, dead_stream=names.dead, stream=names.stream)[0].id
    assert (
        replay(redis_client, dead_stream=names.dead, stream=names.stream, ids=[first_dead_id]) == 1
    )
    [left] = dead_entries(redis_client, names)
    assert left["envelope"] == json.dumps(second)


def test_t43_purge_removes_every_entry_of_that_user_only(redis_client: Redis, names: Names) -> None:
    # Review 🟠2. Red when: a deleted user's events (unit titles, file keys) stay in the dead
    # letter, which is never trimmed.
    gone, kept = uuid.uuid4(), uuid.uuid4()
    add_dead(redis_client, names, stream=names.stream, envelope=json.dumps(uploaded(gone)))
    add_dead(redis_client, names, stream="events.ai", envelope=json.dumps(uploaded(gone)))
    add_dead(redis_client, names, stream=names.stream, envelope=json.dumps(uploaded(kept)))
    add_dead(redis_client, names, stream=names.stream, envelope="not json")
    # Review 🟢E: someone else's event holding a key of the deleted user (user_mismatch), and
    # one that broke the contract with the id in capitals.
    add_dead(
        redis_client, names, stream=names.stream, envelope=json.dumps(uploaded(key_owner=gone))
    )
    upper = {**uploaded(), "user_id": str(gone).upper()}
    add_dead(redis_client, names, stream=names.stream, envelope=json.dumps(upper))
    assert purge_user(redis_client, dead_stream=names.dead, user_id=gone) == 4
    left = dead_entries(redis_client, names)
    assert len(left) == 2
    assert str(gone) not in json.dumps(left)


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_REDIS_URL", TEST_REDIS_URL)


@pytest.mark.usefixtures("cli_env")
def test_t43_list_prints_ids_of_this_stream_and_no_payload(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    event = uploaded()
    dead_from_core(redis_client, names, session_factory, event)
    add_dead(redis_client, names, stream="events.ai", envelope=json.dumps(uploaded()))
    add_dead(redis_client, names, stream=names.stream, envelope="x" * 300)
    code = dead_letter.main(["--stream", names.stream, "--dead-stream", names.dead, "list"])
    assert code == 0
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert len(lines) == 2  # the events.ai entry is core-api's
    assert event["event_id"] in lines[0]
    assert DOCUMENT_UPLOADED in lines[0] and "no_handler" in lines[0]
    assert event["payload"]["object_key"] not in out  # pyright: ignore[reportIndexIssue]
    assert event["user_id"] not in out
    assert "x" * 300 not in out


@pytest.mark.usefixtures("cli_env")
def test_t43_cli_replay_and_purge(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    event = uploaded()
    dead_from_core(redis_client, names, session_factory, event)
    args = ["--stream", names.stream, "--dead-stream", names.dead]
    assert dead_letter.main([*args, "replay", "--all"]) == 0
    assert dead_entries(redis_client, names) == []
    # The replayed entry is dead again: still no handler.
    assert make_consumer(redis_client, names, session_factory, {}).run_once() == ["dead"]
    assert len(dead_entries(redis_client, names)) == 1
    assert dead_letter.main([*args, "purge", "--user", event["user_id"]]) == 0  # pyright: ignore[reportArgumentType]
    assert dead_entries(redis_client, names) == []


def test_t43_cli_without_redis_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # Review 🟢12: fail closed, with a message, rather than a traceback or a default Redis.
    monkeypatch.delenv("AI_REDIS_URL", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        dead_letter.main(["list"])
    assert exit_info.value.code not in (0, None)


def test_t43_replay_needs_ids_or_all() -> None:
    with pytest.raises(SystemExit):
        dead_letter.main(["replay"])
