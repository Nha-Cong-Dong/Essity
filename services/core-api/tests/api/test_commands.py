"""T9.2e: `POST /v1/commands` and `POST /v1/commands/{id}/undo` over the real tables (US-18 AC3,
AC4, AC5, AC8, AC9; ADR-0030). The service's own rules are in tests/commands; here the HTTP
shape, the parser leg (a double that counts calls), isolation, the unverified user and the
suggestion filter."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_suggestions import TODAY, headers_of, subject_with

from clock import FROZEN_NOW
from cmd_world import CmdWorld
from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import NotGraded
from core_api.clients.parse_command_contract import ParseCommandReply
from core_api.db.models import CommandLog, UnitSection, User
from core_api.main import app
from core_api.repositories.auth_session import AuthSessionRepository


class FakeAi:
    """Answers every parse with `result` (or a failure), and keeps what it was asked."""

    def __init__(self) -> None:
        self.result: dict[str, Any] = {"kind": "unclear", "reason": "ambiguous"}
        self.failure: NotGraded | None = None
        self.payloads: list[dict[str, Any]] = []

    def parse_command(self, payload: dict[str, Any]) -> ParseCommandReply | NotGraded:
        self.payloads.append(payload)
        if self.failure is not None:
            return self.failure
        return ParseCommandReply(
            provider="fake",
            model="fake",
            prompt_version="v1",
            run_id=uuid.uuid4(),
            llm_call_id=uuid.uuid4(),
            result=self.result,
        )


@pytest.fixture
def ai() -> Iterator[FakeAi]:
    fake = FakeAi()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


SESSION = str(uuid.UUID(int=7))
World = tuple[CmdWorld, dict[str, str]]


def post(
    client: TestClient, headers: dict[str, str], body: dict[str, Any], cid: uuid.UUID | None = None
) -> Any:
    payload = {"command_id": str(cid or uuid.uuid4()), "screen_session_id": SESSION, **body}
    return client.post("/v1/commands", json=payload, headers=headers)


def exclude(section: object) -> list[dict[str, object]]:
    return [{"kind": "section_exclude", "sections": [str(section.id)]}]  # type: ignore[attr-defined]


def undo(client: TestClient, headers: dict[str, str], cid: uuid.UUID) -> Any:
    return client.post(f"/v1/commands/{cid}/undo", headers=headers)


def log_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(CommandLog)) or 0


@pytest.fixture
def world(db_session: Session, two_users: tuple[User, User]) -> World:
    cw = CmdWorld(db_session, two_users[0])
    return cw, headers_of(db_session, two_users[0])


def test_ac4_ops_apply_once_and_retry_answers_from_the_log(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # AC4, AC9
    cw, h = world
    cid = uuid.uuid4()
    body = {"ops": exclude(cw.leaf1)}
    first = post(client, h, body, cid)
    assert first.status_code == 200, first.text
    out = first.json()
    assert out["status"] == "applied" and out["affected"] == 1 and out["replayed"] is False
    assert out["op_kinds"] == ["section_exclude"] and out["diff"][0]["kind"] == "section"
    again = post(client, h, body, cid)
    assert again.status_code == 200 and again.json()["replayed"] is True
    assert again.json()["diff"] == out["diff"]
    assert log_count(cw.db) == 1 and ai.payloads == []
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is True


def test_ac8_text_is_parsed_once_even_on_retry(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # AC4, AC8
    cw, h = world
    ai.result = {"kind": "section_exclude", "sections": [str(cw.leaf2.id)]}
    cid = uuid.uuid4()
    body = {"text": "bỏ mục 1.2", "subject_id": str(cw.subject.id)}
    for _ in range(2):
        assert post(client, h, body, cid).status_code == 200
    assert len(ai.payloads) == 1 and log_count(cw.db) == 1
    cw.db.refresh(cw.leaf2)
    assert cw.leaf2.excluded is True


def test_y1_parser_gets_cards_and_sections_in_display_order(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # T9.1 Y1
    cw, h = world
    for i, card in enumerate((cw.cards[1], cw.cards[2], cw.cards[0])):  # oldest first
        card.created_at = FROZEN_NOW - timedelta(hours=3 - i)
    cw.db.flush()
    post(client, h, {"text": "làm gì đó", "subject_id": str(cw.subject.id)})
    payload = ai.payloads[0]
    assert [s["id"] for s in payload["sections"]] == [
        str(cw.parent.id),
        str(cw.leaf1.id),
        str(cw.leaf2.id),
    ]
    shown_cards = [cw.cards[1], cw.cards[2], cw.cards[0]]
    assert [c["id"] for c in payload["cards"]] == [str(c.id) for c in shown_cards]
    assert payload["user_id"] == str(cw.user.id) and payload["command"] == "làm gì đó"
    assert all(set(c) == {"id", "title"} for c in payload["cards"])  # AC7: ids and titles only


def test_y1_cards_follow_their_section_then_the_loose_ones(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # T9.1 Y1
    cw, h = world
    old, mid, new = cw.cards
    for i, card in enumerate((old, mid, new)):
        card.created_at = FROZEN_NOW - timedelta(hours=3 - i)
    for card, section in ((old, cw.leaf2), (new, cw.leaf1)):  # `mid` is in no section
        cw.db.add(
            UnitSection(
                user_id=cw.user.id, subject_id=cw.subject.id, unit_id=card.id, section_id=section.id
            )
        )
    cw.db.flush()
    post(client, h, {"text": "x", "subject_id": str(cw.subject.id)})
    assert [c["id"] for c in ai.payloads[0]["cards"]] == [str(c.id) for c in (new, old, mid)]


def test_ac3_unclear_runs_and_logs_nothing(client: TestClient, ai: FakeAi, world: World) -> None:
    cw, h = world  # AC3
    ai.result = {"kind": "unclear", "reason": "unknown_target"}
    r = post(client, h, {"text": "xóa hết", "subject_id": str(cw.subject.id)})
    assert r.status_code == 200 and r.json() == {"status": "unclear", "reason": "unknown_target"}
    assert log_count(cw.db) == 0


@pytest.mark.parametrize(
    ("failure", "status", "detail"),
    [
        (NotGraded("quota", "quota_hard_cap"), 429, "quota_hard_cap"),
        (NotGraded("disabled", "grading_disabled"), 503, "ai_disabled"),
        (NotGraded("unavailable", "timeout"), 503, "parse_unavailable"),
        (NotGraded("invalid", "response_schema"), 502, "parse_invalid"),
    ],
)
def test_ac8_parse_failures_have_their_own_codes_and_write_nothing(
    client: TestClient, ai: FakeAi, world: World, failure: NotGraded, status: int, detail: str
) -> None:  # AC8
    cw, h = world
    ai.failure = failure
    r = post(client, h, {"text": "bỏ mục 1.1", "subject_id": str(cw.subject.id)})
    assert r.status_code == status and r.json() == {"detail": detail}
    assert log_count(cw.db) == 0
    # editing by hand (ops the client parsed) still works when the AI is off
    assert post(client, h, {"ops": exclude(cw.leaf1)}).status_code == 200


def test_text_in_another_users_subject_is_404_before_any_parse(
    client: TestClient, ai: FakeAi, world: World, db_session: Session, two_users: tuple[User, User]
) -> None:
    _, h = world
    bob = CmdWorld(db_session, two_users[1])
    r = post(client, h, {"text": "bỏ", "subject_id": str(bob.subject.id)})
    assert r.status_code == 404 and r.json() == {"detail": "subject_not_found"}
    assert ai.payloads == []


def test_unverified_email_is_403_on_both_routes(
    client: TestClient, ai: FakeAi, db_session: Session, unverified_user: User
) -> None:
    token, _ = AuthSessionRepository(db_session).create(unverified_user.id, datetime.now(UTC))
    db_session.flush()
    h = {"Authorization": f"Bearer {token}"}
    ops = [{"kind": "section_exclude", "sections": [str(uuid.uuid4())]}]
    r = post(client, h, {"ops": ops})
    assert r.status_code == 403 and r.json() == {"detail": "email_not_verified"}
    assert undo(client, h, uuid.uuid4()).status_code == 403
    assert post(client, {}, {"ops": ops}).status_code == 401


def test_ac4_two_users_never_reach_each_others_data(
    client: TestClient, ai: FakeAi, db_session: Session, two_users: tuple[User, User]
) -> None:  # AC4 isolation
    alice, bob = two_users
    a, b = CmdWorld(db_session, alice), CmdWorld(db_session, bob)
    ha, hb = headers_of(db_session, alice), headers_of(db_session, bob)
    cid = uuid.uuid4()
    assert post(client, ha, {"ops": exclude(a.leaf1)}, cid).status_code == 200
    theirs = post(client, hb, {"ops": exclude(a.leaf1)})  # B cannot touch A's section
    assert theirs.status_code == 404 and theirs.json() == {"detail": "not_owned"}
    nothing = [{"kind": "section_exclude", "sections": [str(uuid.uuid4())]}]
    assert post(client, hb, {"ops": nothing}).json() == theirs.json()  # no tell-tale difference
    assert undo(client, hb, cid).status_code == 404  # nor undo A's command
    # the same command_id is a different command for B: no answer from A's row
    mine = post(client, hb, {"ops": exclude(b.leaf1)}, cid)
    assert mine.status_code == 200 and mine.json()["replayed"] is False
    db_session.refresh(a.leaf1)
    assert a.leaf1.excluded is True and log_count(db_session) == 2


def test_ac4_command_id_with_another_request_is_409(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, h = world
    cid = uuid.uuid4()
    assert post(client, h, {"ops": exclude(cw.leaf1)}, cid).status_code == 200
    r = post(client, h, {"ops": exclude(cw.leaf2)}, cid)
    assert r.status_code == 409 and r.json() == {"detail": "command_id_reused"}


@pytest.mark.parametrize(
    "ops",
    [
        [{"kind": "section_set_pages", "section": str(uuid.uuid4()), "from_page": 1, "to_page": 2}],
        [{"kind": "delete_everything"}],
        [{"kind": "unclear", "reason": "ambiguous"}],
    ],
)
def test_ac6_ops_outside_the_fixed_list_are_422(
    client: TestClient, ai: FakeAi, world: World, ops: list[dict[str, Any]]
) -> None:  # AC6
    cw, h = world
    r = post(client, h, {"ops": ops})
    assert r.status_code == 422 and r.json() == {"detail": "unsupported"}
    assert log_count(cw.db) == 0


def test_the_request_has_exactly_one_of_text_or_ops(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, h = world
    sid = str(cw.subject.id)
    bodies: list[dict[str, Any]] = [
        {},
        {"text": "a", "subject_id": sid, "ops": exclude(cw.leaf1)},
        {"text": "a"},
        {"text": "   ", "subject_id": sid},
        {"ops": []},
        {"text": "x" * 501, "subject_id": sid},
    ]
    for body in bodies:
        assert post(client, h, body).status_code == 422, body
    assert ai.payloads == [] and log_count(cw.db) == 0


def test_ac5_undo_not_latest_changed_after_and_twice(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # AC5
    cw, h = world
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    post(client, h, {"ops": exclude(cw.leaf1)}, c1)
    post(client, h, {"ops": exclude(cw.leaf2)}, c2)
    older = undo(client, h, c1)
    assert older.status_code == 409 and older.json() == {"detail": "not_latest"}
    done = undo(client, h, c2)
    assert done.status_code == 200 and done.json()["status"] == "undone"
    assert done.json()["replayed"] is False
    cw.db.refresh(cw.leaf2)
    assert cw.leaf2.excluded is False
    assert undo(client, h, c2).json()["replayed"] is True
    cw.leaf1.title = "sửa tay"  # a hand edit after the command moves the revision
    cw.db.flush()
    moved = undo(client, h, c1)
    assert moved.status_code == 409 and moved.json() == {"detail": "changed_after"}
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is True
    assert undo(client, h, uuid.uuid4()).status_code == 404


def test_the_retry_of_an_undone_command_says_so(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, h = world
    cid = uuid.uuid4()
    body = {"ops": exclude(cw.leaf1)}
    post(client, h, body, cid)
    undo(client, h, cid)
    r = post(client, h, body, cid)
    assert r.status_code == 200 and r.json()["status"] == "undone" and r.json()["replayed"]
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is False  # the retry did not apply it again


def test_ac9_the_log_row_holds_the_command_and_its_inverse(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # AC9
    cw, h = world
    cid = uuid.uuid4()
    post(client, h, {"ops": exclude(cw.leaf1)}, cid)
    row = cw.db.scalars(select(CommandLog).where(CommandLog.command_id == cid)).one()
    assert row.user_id == cw.user.id and str(row.screen_session_id) == SESSION
    assert row.ops_json[0]["kind"] == "section_exclude" and row.inverse_json


def three_subjects(db: Session, user: User) -> tuple[Any, Any, Any]:
    a, _, _ = subject_with(db, user, "A", [{"weight": 10}], days=5)
    b, _, _ = subject_with(db, user, "B", [{"weight": 10}], days=30)
    c, _, _ = subject_with(db, user, "C", [{"weight": 10}], days=60)
    return a, b, c


def shown(client: TestClient, h: dict[str, str]) -> list[str]:
    body = client.get("/v1/suggestions", headers=h).json()
    return [s["subject_name"] for s in body["suggestions"]]


def test_suggestion_filter_only_subject_until_date(
    client: TestClient,
    ai: FakeAi,
    db_session: Session,
    two_users: tuple[User, User],
    set_now: Callable[..., None],
) -> None:  # US-15 AC9
    alice = two_users[0]
    h = headers_of(db_session, alice)
    _, _, c = three_subjects(db_session, alice)
    assert shown(client, h) == ["A", "B"]
    until = (TODAY + timedelta(days=2)).isoformat()
    ops = [{"kind": "suggest_only_subject", "subject": str(c.id), "until": until}]
    assert post(client, h, {"ops": ops}).status_code == 200
    assert shown(client, h) == ["C"]  # the filter comes before the ranking
    set_now(FROZEN_NOW + timedelta(days=2))  # the last day it holds
    assert shown(client, h) == ["C"]
    set_now(FROZEN_NOW + timedelta(days=3))  # it has ended
    assert shown(client, h) == ["A", "B"]


def test_suggestion_filter_defer_makes_room_and_undo_lifts_it(
    client: TestClient,
    ai: FakeAi,
    db_session: Session,
    two_users: tuple[User, User],
    set_now: Callable[..., None],
) -> None:
    alice, bob = two_users
    h, hb = headers_of(db_session, alice), headers_of(db_session, bob)
    a, _, _ = three_subjects(db_session, alice)
    until = (TODAY + timedelta(days=4)).isoformat()
    ops = [{"kind": "suggest_defer_subject", "subject": str(a.id), "until": until}]
    cid = uuid.uuid4()
    assert post(client, h, {"ops": ops}, cid).status_code == 200
    assert shown(client, h) == ["B", "C"]  # A hidden, C takes its place in the top two
    assert shown(client, hb) == []  # another user's suggestions are untouched
    set_now(FROZEN_NOW + timedelta(days=4))
    assert shown(client, h) == ["A", "B"]
    set_now(FROZEN_NOW)
    assert undo(client, h, cid).status_code == 200
    assert shown(client, h) == ["A", "B"]
