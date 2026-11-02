"""T8.5 (US-03 AC4/AC9, US-06 AC5/AC8, US-16 AC11; plan commits 5-6): a review session that mixes
cards and practice questions. A practice question is answered through `/v1/practice` (its own
schedule); grading a card never moves `practice_state`, grading a practice question never moves
`memory_state`."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_t28_today_api import Space, today
from test_t84_practice_api import RUBRIC, FakeAi, Open

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.api.ping import get_ai_client
from core_api.db.models import (
    Attempt,
    MemoryState,
    PracticeLog,
    PracticeState,
    Question,
    ReviewLog,
    User,
)
from core_api.main import app
from core_api.repositories.question import QuestionUnitRepository
from core_api.repositories.review import (
    AttemptRepository,
    QuestionNotAskableError,
    ReviewSessionRepository,
)
from core_api.security.rate_limit import get_rate_limiter
from grader_stub import Stub
from practice_bench import Bench, schedule

OVERDUE = FROZEN_NOW - timedelta(days=3)
Headers = dict[str, str]


class Both(FakeAi):
    """One ai client for both: cards graded by the stub, practice by the scripted fake."""

    def __init__(self) -> None:
        super().__init__()
        self.cards = Stub()

    def grade(self, payload: Any) -> Any:
        return self.cards.grade(payload)


@pytest.fixture
def ai() -> Iterator[Both]:
    fake = Both()
    app.dependency_overrides[get_ai_client] = lambda: fake
    app.dependency_overrides[get_rate_limiter] = lambda: Open()
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)
    app.dependency_overrides.pop(get_rate_limiter, None)


class World:
    def __init__(self, client: TestClient, session: Session) -> None:
        self.client, self.session = client, session
        self.user, self.headers = signed_in(session)
        self.bench = Bench(session, self.user)
        self.space = Space(session, self.user)

    def practice(self, due: bool = True) -> Question:
        q = self.bench.ready(rubric=RUBRIC, answer_text="Bắt tay ba bước.", answer_origin="bank")
        card_unit = self.bench.card(self.bench._ready)  # type: ignore[arg-type]  # noqa: SLF001
        QuestionUnitRepository(self.session, self.user.id).link(q.id, card_unit.id)
        if due:
            schedule(self.session, self.user, q, OVERDUE)
        return q

    def card(self, title: str = "TCP") -> tuple[uuid.UUID, uuid.UUID]:
        unit_id, question = self.space.question(self.space.subject(title), title)
        self.space.scheduled(unit_id, due_in_days=-1)
        return unit_id, question.id

    def start(self) -> dict[str, Any]:
        response = self.client.post("/v1/review-sessions", json={}, headers=self.headers)
        assert response.status_code == 201, response.text
        return response.json()

    def current(self, session_id: str) -> dict[str, Any]:
        response = self.client.get(
            f"/v1/review-sessions/{session_id}/current", headers=self.headers
        )
        assert response.status_code == 200, response.text
        return response.json()

    def answer_card(self, session_id: str) -> None:
        now = self.current(session_id)
        assert now["question"]["kind"] == "card"
        made = self.client.post(f"/v1/review-sessions/{session_id}/attempts", headers=self.headers)
        assert made.status_code == 201, made.text
        sent = self.client.post(
            f"/v1/attempts/{made.json()['id']}/submit",
            json={"answer_text": "x", "dont_remember": False},
            headers=self.headers,
        )
        assert sent.status_code == 200, sent.text

    def answer_practice(self, question_id: str) -> None:
        opened = self.client.post(
            f"/v1/practice/questions/{question_id}/open", headers=self.headers
        )
        assert opened.status_code == 200, opened.text
        sent = self.client.post(
            f"/v1/practice/attempts/{opened.json()['attempt_id']}/submit",
            json={"answer_text": "SYN, SYN-ACK, ACK", "dont_remember": False},
            headers=self.headers,
        )
        assert sent.status_code == 200, sent.text

    def tables(self) -> dict[str, list[tuple[Any, ...]]]:
        self.session.expire_all()
        out: dict[str, list[tuple[Any, ...]]] = {}
        for name, model, columns in (
            ("review_log", ReviewLog, (ReviewLog.id, ReviewLog.unit_id, ReviewLog.rating)),
            (
                "memory_state",
                MemoryState,
                (MemoryState.unit_id, MemoryState.due, MemoryState.stability),
            ),
            (
                "practice_log",
                PracticeLog,
                (PracticeLog.id, PracticeLog.question_id, PracticeLog.rating),
            ),
            (
                "practice_state",
                PracticeState,
                (PracticeState.question_id, PracticeState.due, PracticeState.stability),
            ),
        ):
            rows = self.session.execute(select(*columns)).all()
            out[name] = sorted((tuple(r) for r in rows), key=str)
            assert model is not None
        return out


@pytest.fixture
def world(client: TestClient, db_session: Session, ai: Both) -> World:
    return World(client, db_session)


def test_session_items_equal_today_review_items(world: World) -> None:
    world.card()
    world.practice()
    shown = [i["question_id"] for i in today(world.client, world.headers)["review"]["items"]]
    started = world.start()
    assert started["total"] == len(shown) == 2
    from core_api.repositories.review import ReviewSessionItemRepository

    items = ReviewSessionItemRepository(world.session, world.user.id).of_session(
        uuid.UUID(started["id"])
    )
    assert [str(i.question_id) for i in items] == shown


def test_practice_step_is_marked_and_has_no_unit_to_skip(world: World) -> None:
    q = world.practice()
    started = world.start()
    now = world.current(started["id"])
    assert now["question"]["id"] == str(q.id)
    assert now["question"]["kind"] == "practice" and now["question"]["unit_ids"] == []
    assert now["attempt"] is None and now["question"]["reason"]["kind"] == "review"


def test_review_attempt_route_refuses_practice_step(world: World) -> None:
    world.practice()
    started = world.start()
    before = world.tables()
    response = world.client.post(
        f"/v1/review-sessions/{started['id']}/attempts", headers=world.headers
    )
    assert response.status_code == 409 and response.json()["detail"] == "practice_question"
    assert world.tables() == before
    assert world.session.scalars(select(Attempt)).all() == []


def test_open_draft_refuses_a_bank_question_at_the_repository(world: World) -> None:
    q = world.practice()
    sitting = ReviewSessionRepository(world.session, world.user.id).start(
        FROZEN_NOW.date(), FROZEN_NOW
    )
    with pytest.raises(QuestionNotAskableError):
        AttemptRepository(world.session, world.user.id).open_draft(sitting.id, q.id)


def test_mixed_session_card_grade_leaves_practice_state(world: World) -> None:
    world.card()
    p = world.practice()
    sid = world.start()["id"]
    world.answer_practice(str(p.id))  # practice first: it is the riskier of the two
    before = world.tables()
    world.answer_card(sid)
    after = world.tables()
    assert after["review_log"] != before["review_log"]  # the card was graded
    assert after["memory_state"] != before["memory_state"]
    assert after["practice_state"] == before["practice_state"]
    assert after["practice_log"] == before["practice_log"]


def test_mixed_session_practice_grade_leaves_memory_state(world: World) -> None:
    world.card()
    p = world.practice()
    world.start()
    before = world.tables()
    world.answer_practice(str(p.id))
    after = world.tables()
    assert after["practice_log"] != before["practice_log"]
    assert after["memory_state"] == before["memory_state"]
    assert after["review_log"] == before["review_log"]


def test_whole_mixed_session_counts_and_stops_completed(world: World) -> None:
    world.card()
    p = world.practice()
    sid = world.start()["id"]
    assert world.current(sid)["total"] == 2
    cards_before = world.tables()
    world.answer_practice(str(p.id))
    after_practice = world.tables()
    assert after_practice["memory_state"] == cards_before["memory_state"]
    assert after_practice["review_log"] == cards_before["review_log"]
    now = world.current(sid)
    assert now["done"] is False and now["position"] == 2 and now["question"]["kind"] == "card"
    assert now["ungraded"] == []  # a practice answer is never a review "chấm lại"
    world.answer_card(sid)
    after_card = world.tables()
    assert after_card["practice_state"] == after_practice["practice_state"]
    assert after_card["practice_log"] == after_practice["practice_log"]
    assert world.current(sid)["done"] is True
    stopped = world.client.post(f"/v1/review-sessions/{sid}/stop", headers=world.headers).json()
    assert (stopped["answered"], stopped["total"]) == (2, 2)
    assert stopped["next_day"] is not None  # the practice schedule moved on, and counts


def test_practice_answered_before_the_session_does_not_count(world: World) -> None:
    p = world.practice()
    world.answer_practice(str(p.id))  # now a later due date: not due, not in a new session
    world.card()
    sid = world.start()["id"]
    assert world.current(sid)["total"] == 1


def test_skip_after_practice_answered_does_not_reask_it(world: World) -> None:
    u1, _ = world.card("A")
    world.card("B")
    p = world.practice()
    sid = world.start()["id"]
    world.answer_practice(str(p.id))
    skipped = world.client.post(
        f"/v1/units/{u1}/skip", json={"review_session_id": sid}, headers=world.headers
    )
    assert skipped.status_code == 200, skipped.text
    nxt = skipped.json()["next"]
    assert nxt["done"] is False and nxt["question"]["id"] != str(p.id)
    assert nxt["position"] == 2  # the answered practice question is position 1
    shown = today(world.client, world.headers)["in_progress"]
    assert shown is not None and shown["position"] == 2


def test_practice_only_day_whole_session(world: World) -> None:
    a, b = world.practice(), world.practice()
    body = today(world.client, world.headers)
    assert body["state"] == "ready" and body["session"]["question_count"] == 2
    sid = world.start()["id"]
    for q in (a, b):
        assert world.current(sid)["question"]["kind"] == "practice"
        world.answer_practice(str(q.id))
        world.session.expire_all()
    assert world.current(sid)["done"] is True
    stopped = world.client.post(f"/v1/review-sessions/{sid}/stop", headers=world.headers).json()
    assert (stopped["answered"], stopped["total"]) == (2, 2)
    assert today(world.client, world.headers)["in_progress"] is None


def test_a_practice_question_taken_out_mid_session_drops_out(world: World) -> None:
    world.card()
    p = world.practice()
    sid = world.start()["id"]
    state = world.session.scalars(
        select(PracticeState).where(PracticeState.question_id == p.id)
    ).one()
    state.removed_at = FROZEN_NOW
    world.session.flush()
    assert world.current(sid)["total"] == 1


def test_unverified_account_is_refused_everywhere(
    client: TestClient, db_session: Session, ai: Both
) -> None:
    user: User
    user, headers = signed_in(db_session, verified=False)
    sid = uuid.uuid4()
    calls = [
        client.post("/v1/review-sessions", json={}, headers=headers),
        client.get(f"/v1/review-sessions/{sid}/current", headers=headers),
        client.post(f"/v1/review-sessions/{sid}/attempts", headers=headers),
        client.post(f"/v1/review-sessions/{sid}/stop", headers=headers),
        client.post(f"/v1/units/{uuid.uuid4()}/skip", json={}, headers=headers),
    ]
    assert [c.status_code for c in calls] == [403] * 5
    assert user.id is not None
