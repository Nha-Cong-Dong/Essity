"""T4.4: `python -m core_api.messaging.dead_letter purge --user <uuid>` removes what the dead
letter keeps of one user (T6.3 calls it when an account is deleted). Real Redis."""

import uuid
from typing import cast

import pytest
from redis import Redis

from core_api.messaging.dead_letter import main, purge_user

Entries = list[tuple[bytes, dict[bytes, bytes]]]


@pytest.fixture
def dead(stream: str, redis_client: Redis) -> str:
    return f"{stream}.dead"


def add(redis: Redis, dead_stream: str, envelope: str | bytes) -> None:
    redis.xadd(dead_stream, {"envelope": envelope, "reason": "Boom"})


def left(redis: Redis, dead_stream: str) -> list[bytes]:
    entries = cast(Entries, redis.xrange(dead_stream))
    return [fields[b"envelope"] for _, fields in entries]


def test_purge_removes_every_entry_that_mentions_the_user(redis_client: Redis, dead: str) -> None:
    # Red when: an account deleted under T6.3 leaves its unit titles and file keys in the dead
    # letter for ever (it is never trimmed).
    user, other = uuid.uuid4(), uuid.uuid4()
    add(redis_client, dead, f'{{"user_id": "{user}", "x": "own event"}}')
    add(redis_client, dead, f'{{"user_id": "{other}", "x": "someone else"}}')
    add(redis_client, dead, f'{{"user_id": "{other}", "k": "users/{user}/subjects/s/a.pdf"}}')
    add(redis_client, dead, "not json, but names " + str(user).upper())
    add(redis_client, dead, b"\xff\xfe" + str(user).encode())
    try:
        assert purge_user(redis_client, dead_stream=dead, user_id=user) == 4
        assert left(redis_client, dead) == [
            f'{{"user_id": "{other}", "x": "someone else"}}'.encode()
        ]
    finally:
        redis_client.delete(dead)


def test_purge_of_a_user_with_nothing_there_removes_nothing(redis_client: Redis, dead: str) -> None:
    # Red when: purge removes entries it was not asked to.
    add(redis_client, dead, f'{{"user_id": "{uuid.uuid4()}"}}')
    try:
        assert purge_user(redis_client, dead_stream=dead, user_id=uuid.uuid4()) == 0
        assert len(left(redis_client, dead)) == 1
    finally:
        redis_client.delete(dead)


def test_purge_on_a_missing_stream_is_zero(redis_client: Redis, dead: str) -> None:
    # Red when: the first purge, before any entry was ever dead-lettered, raises.
    assert purge_user(redis_client, dead_stream=dead, user_id=uuid.uuid4()) == 0


def test_command_line_purge_prints_how_many(
    redis_client: Redis,
    dead: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: `purge --user` is not wired to purge_user, or accepts text that is not a uuid.
    user = uuid.uuid4()
    add(redis_client, dead, f'{{"user_id": "{user}"}}')
    monkeypatch.setattr("core_api.messaging.dead_letter.DEAD_STREAM", dead)
    try:
        assert main(["purge", "--user", str(user)]) == 0
        assert capsys.readouterr().out == "purged 1\n"
        with pytest.raises(SystemExit):
            main(["purge", "--user", "not-a-uuid"])
    finally:
        redis_client.delete(dead)
