"""T7.8 (US-02b AC9, AC13): two real connections on one session's drafts. The first holds the
session lock (a slowed outbox write) while the second arrives: the second waits, then sees the
committed state. No deadlock, no second revision, no second event."""

import threading
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import pytest
from draft_world import World
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.session import get_session
from core_api.domain import unit_review
from core_api.handlers.session_result_v2 import OnSubmissionProcessed
from core_api.main import app
from core_api.repositories.auth_session import AuthSessionRepository
from fake_storage import FakeStorage

SetNow = Callable[[datetime], None]


@pytest.fixture
def committed(
    engine: Engine, fake_storage: FakeStorage
) -> Iterator[tuple[World, list[dict[str, str]], list[str]]]:
    """A session with three committed drafts and two logins (one per click, so they do not
    serialize on a shared login row)."""
    with Session(engine, expire_on_commit=False) as setup:
        user, first = signed_in(setup)
        token, _ = AuthSessionRepository(setup).create(user.id, datetime.now().astimezone())
        world = World(setup, user, fake_storage)
        key = world.put([world.draft(1), world.draft(2), world.draft(3)])
        OnSubmissionProcessed(fake_storage)(setup, world.processed(key))
        rows = setup.execute(
            text("SELECT id, version FROM knowledge_unit WHERE user_id = :u ORDER BY title"),
            {"u": user.id},
        ).all()
        ids = [f"{r.id}:{r.version}" for r in rows]
        setup.commit()
    try:
        yield world, [first, {"Authorization": f"Bearer {token}"}], ids
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM outbox WHERE user_id = :u"), {"u": world.user.id})
            connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": world.user.id})


@pytest.fixture
def own_sessions(engine: Engine) -> Iterator[None]:
    def real_session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as own:
            try:
                yield own
                own.commit()
            except BaseException:
                own.rollback()
                raise

    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = real_session
    yield
    if previous is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = previous


def slow_outbox(monkeypatch: pytest.MonkeyPatch) -> None:
    real = unit_review._enqueue_unit_saved  # pyright: ignore[reportPrivateUsage]

    def slow(*args: Any, **kwargs: Any) -> None:
        time.sleep(0.4)  # the first request holds the session lock while the second arrives
        real(*args, **kwargs)

    monkeypatch.setattr(unit_review, "_enqueue_unit_saved", slow)


def run_two(calls: list[Callable[[], Any]]) -> list[Any]:
    results: list[Any] = []

    def go(call: Callable[[], Any]) -> None:
        try:
            results.append(call())
        except BaseException as error:  # noqa: BLE001 - a deadlock would surface here
            results.append(error)

    threads = [threading.Thread(target=go, args=(c,)) for c in calls]
    for thread in threads:
        thread.start()
        time.sleep(0.1)
    for thread in threads:
        thread.join(timeout=15)
    return results


def count(engine: Engine, sql: str, user_id: object) -> int:
    with engine.connect() as connection:
        return connection.execute(text(sql), {"u": user_id}).scalar_one()


@pytest.mark.usefixtures("own_sessions")
def test_ac9_two_saves_of_the_same_cards_one_wins_the_other_saves_nothing(
    client: TestClient,
    engine: Engine,
    committed: tuple[World, list[dict[str, str]], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: both requests write revision 1 (unique violation) or both announce the cards.
    world, heads, ids = committed
    slow_outbox(monkeypatch)
    body = {"units": [{"unit_id": i.split(":")[0], "version": int(i.split(":")[1])} for i in ids]}
    url = f"/v1/sessions/{world.study.id}/drafts/save"
    results = run_two([lambda h=h: client.post(url, json=body, headers=h) for h in heads])
    assert [r.status_code for r in results] == [200, 200]
    assert sorted(len(r.json()["saved"]) for r in results) == [0, 3]
    user = world.user.id
    assert (
        count(engine, "SELECT count(*) FROM unit_revision WHERE user_id = :u AND rev = 1", user)
        == 3
    )
    sql = "SELECT count(*) FROM outbox WHERE user_id = :u AND event_type = 'unit.saved.v1'"
    assert count(engine, sql, user) == 3
    assert count(engine, "SELECT sum(units_saved) FROM study_ledger WHERE user_id = :u", user) == 3


@pytest.mark.usefixtures("own_sessions")
def test_ac9_a_merge_and_a_save_of_one_session_do_not_deadlock(
    client: TestClient,
    engine: Engine,
    committed: tuple[World, list[dict[str, str]], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: merge locks the cards before the session while Save locks the session first
    # (Postgres answers DeadlockDetected, a 500 or an exception here).
    world, heads, ids = committed
    slow_outbox(monkeypatch)
    plain = [i.split(":")[0] for i in ids]
    save = {"units": [{"unit_id": plain[0], "version": 1}, {"unit_id": plain[1], "version": 1}]}
    results = run_two(
        [
            lambda: client.post(
                f"/v1/sessions/{world.study.id}/drafts/save", json=save, headers=heads[0]
            ),
            lambda: client.post(
                f"/v1/sessions/{world.study.id}/drafts/merge",
                json={"unit_ids": plain[:2]},
                headers=heads[1],
            ),
        ]
    )
    assert all(not isinstance(r, BaseException) for r in results), results
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409], codes  # the save won; the merge then saw saved cards
