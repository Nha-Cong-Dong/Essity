"""T9.2e: two real requests on the same card at once (US-18 AC4, AC5): the locks make them take
turns, one answer each, never a 500 and never a half-written command. Each side is a thread with
its own session, like two browser tabs."""

import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from cmd_world import CmdWorld
from core_api.api.deps import get_storage
from core_api.api.ping import get_ai_client
from core_api.config import get_settings
from core_api.db.session import get_session
from core_api.main import app
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.user import UserRepository
from core_api.security.client_ip import CLIENT_IP_HEADER
from core_api.security.service_token import SERVICE_TOKEN_HEADER
from fake_storage import FakeStorage
from ips import fresh_ip

WEB_TOKEN = "test-web-token-0123456789abcdefghij"
SESSION = str(uuid.UUID(int=9))

Committed = tuple[uuid.UUID, uuid.UUID, dict[str, str]]  # user, card, auth headers


@pytest.fixture
def committed(engine: Engine) -> Iterator[Committed]:
    with Session(engine, expire_on_commit=False) as setup:
        user = UserRepository(setup).create(f"race-{uuid.uuid4().hex[:8]}@example.com")
        user.email_verified_at = datetime.now(UTC)
        setup.flush()
        world = CmdWorld(setup, user)
        token, _ = AuthSessionRepository(setup).create(user.id, datetime.now(UTC))
        ids = (user.id, world.cards[0].id, {"Authorization": f"Bearer {token}"})
        setup.commit()
    try:
        yield ids
    finally:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE command_log DISABLE TRIGGER USER"))
            connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": ids[0]})
            connection.execute(text("ALTER TABLE command_log ENABLE TRIGGER USER"))


@pytest.fixture
def http(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], TestClient]]:
    """A factory of clients whose requests each open their own session on the test database."""
    monkeypatch.setenv("CORE_WEB_TOKEN", WEB_TOKEN)
    get_settings.cache_clear()

    def real_session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    app.dependency_overrides[get_session] = real_session
    app.dependency_overrides.setdefault(get_storage, lambda: FakeStorage())
    app.dependency_overrides[get_ai_client] = lambda: None  # ops are never parsed
    headers = {SERVICE_TOKEN_HEADER: WEB_TOKEN, CLIENT_IP_HEADER: fresh_ip("10")}
    yield lambda: TestClient(app, headers=headers)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_storage, None)
    app.dependency_overrides.pop(get_ai_client, None)


def edit(card: uuid.UUID, words: str) -> dict[str, Any]:
    return {"ops": [{"kind": "card_edit", "card": str(card), "text": words}]}


def send(
    make: Callable[[], TestClient], headers: dict[str, str], path: str, body: dict[str, Any] | None
) -> tuple[int, Any]:
    response = make().post(path, json=body, headers=headers)
    return response.status_code, response.json()


def card_text(engine: Engine, card: uuid.UUID) -> str:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT summary FROM knowledge_unit WHERE id = :c"), {"c": card}
        ).scalar_one()


def log_rows(engine: Engine, user: uuid.UUID) -> list[tuple[str, str]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT status, ops_json->0->>'text' FROM command_log WHERE user_id = :u"),
            {"u": user},
        )
        return [(r[0], r[1]) for r in rows]


def test_ac4_two_commands_on_one_card_take_turns(
    engine: Engine, committed: Committed, http: Callable[[], TestClient]
) -> None:
    user, card, h = committed
    gate = threading.Barrier(2)

    def run(words: str) -> tuple[int, Any]:
        body = {"command_id": str(uuid.uuid4()), "screen_session_id": SESSION, **edit(card, words)}
        gate.wait(timeout=5)
        return send(http, h, "/v1/commands", body)

    with ThreadPoolExecutor(2) as pool:
        first, second = (f.result() for f in [pool.submit(run, "một"), pool.submit(run, "hai")])
    assert first[0] == second[0] == 200, (first, second)
    assert card_text(engine, card) in {"một", "hai"}
    assert sorted(t for _, t in log_rows(engine, user)) == ["hai", "một"]


def test_ac5_undo_races_a_newer_command_on_the_same_card(
    engine: Engine, committed: Committed, http: Callable[[], TestClient]
) -> None:
    user, card, h = committed
    first = uuid.uuid4()
    body = {"command_id": str(first), "screen_session_id": SESSION, **edit(card, "cũ")}
    assert send(http, h, "/v1/commands", body)[0] == 200
    gate = threading.Barrier(2)

    def undo() -> tuple[int, Any]:
        gate.wait(timeout=5)
        return send(http, h, f"/v1/commands/{first}/undo", None)

    def newer() -> tuple[int, Any]:
        body = {"command_id": str(uuid.uuid4()), "screen_session_id": SESSION, **edit(card, "mới")}
        gate.wait(timeout=5)
        return send(http, h, "/v1/commands", body)

    with ThreadPoolExecutor(2) as pool:
        undone, applied = (f.result() for f in [pool.submit(undo), pool.submit(newer)])
    assert applied[0] == 200, applied
    assert card_text(engine, card) == "mới"  # whichever came first, the newer one is last
    if undone[0] == 200:
        assert ("undone", "cũ") in log_rows(engine, user)
    else:  # the newer command landed first: the undo is refused, nothing of it is written
        assert undone[0] == 409 and undone[1]["detail"] in {"not_latest", "changed_after"}, undone
        assert ("applied", "cũ") in log_rows(engine, user)


def card_version(engine: Engine, card: uuid.UUID) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT version FROM knowledge_unit WHERE id = :c"), {"c": card}
        ).scalar_one()


def test_ac5_undo_races_an_edit_on_the_review_screen(
    engine: Engine, committed: Committed, http: Callable[[], TestClient]
) -> None:
    """T9.2d final review: the undo of a command and the review screen's own edit of the same
    card (PATCH with the version it read) never both win, and never leave a mix."""
    user, card, h = committed
    first = uuid.uuid4()
    body = {"command_id": str(first), "screen_session_id": SESSION, **edit(card, "lệnh")}
    assert send(http, h, "/v1/commands", body)[0] == 200
    seen = card_version(engine, card)  # what the screen read after the command
    gate = threading.Barrier(2)

    def undo() -> tuple[int, Any]:
        gate.wait(timeout=5)
        return send(http, h, f"/v1/commands/{first}/undo", None)

    def screen() -> tuple[int, Any]:
        gate.wait(timeout=5)
        response = http().patch(
            f"/v1/drafts/{card}", json={"content": "màn"}, headers={**h, "If-Match": str(seen)}
        )
        return response.status_code, response.json()

    with ThreadPoolExecutor(2) as pool:
        undone, edited = (f.result() for f in [pool.submit(undo), pool.submit(screen)])
    assert {undone[0], edited[0]} <= {200, 409}, (undone, edited)
    assert (undone[0], edited[0]) in {(200, 409), (409, 200)}, (undone, edited)
    final = card_text(engine, card)
    if undone[0] == 200:  # the undo won: the screen's edit was refused as stale
        assert final != "màn" and final != "lệnh"
        assert ("undone", "lệnh") in log_rows(engine, user)
    else:  # the screen won: the undo is refused, the screen's text stays
        assert undone[1]["detail"] == "changed_after" and final.startswith("màn")
        assert ("applied", "lệnh") in log_rows(engine, user)
