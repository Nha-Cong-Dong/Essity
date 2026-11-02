"""T7.14 (US-02b AC6/AC9/AC12, US-03 AC1/AC4): the loop through the real API, one database.

A submission's drafts come back from the result handler, Lưu (POST .../drafts/save) stores
them, and GET /v1/today decides, by the learning day, whether the saved card is in Ôn."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from draft_world import World
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_review_questions import FakeAi

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import KnowledgeUnit
from core_api.domain.learning_day import day_bounds, learning_day
from core_api.handlers.session_result_v2 import OnSubmissionProcessed
from core_api.handlers.unit_saved import ensure_review_question
from fake_storage import FakeStorage

SetNow = Callable[[datetime], None]


# US-02b AC12, US-03 AC4. Red when: a card saved today is in today's Ôn, or the next learning day
# (04:00 boundary) does not bring it, or the card in Ôn has no "why this card".
def test_saved_card_is_in_on_from_the_next_learning_day_only(
    client: TestClient, db_session: Session, fake_storage: FakeStorage, set_now: SetNow
) -> None:
    user, headers = signed_in(db_session)
    world = World(db_session, user, fake_storage)
    key = world.put([world.draft(1)])
    OnSubmissionProcessed(fake_storage)(db_session, world.processed(key))
    db_session.commit()

    base = f"/v1/sessions/{world.study.id}/drafts"
    listed = client.get(base, headers=headers).json()
    assert listed["submission_status"] == "done" and len(listed["drafts"]) == 1
    draft = listed["drafts"][0]
    saved = client.post(
        f"{base}/save",
        json={"units": [{"unit_id": draft["id"], "version": draft["version"]}]},
        headers=headers,
    )
    assert saved.status_code == 200 and saved.json()["saved"] == [draft["id"]]
    db_session.expire_all()
    unit = db_session.scalars(select(KnowledgeUnit)).one()
    assert unit.status == "canonical" and unit.saved_learning_day is not None

    # Save enqueues the job that makes the card's review question; the job's step runs here with
    # the AI double (the only external part).
    assert ensure_review_question(db_session, user.id, unit.id, FakeAi(), lazy=False) == "created"
    db_session.commit()

    tz = ZoneInfo(user.timezone)
    today_day = learning_day(FROZEN_NOW, tz, user.day_start_hour)
    next_start = day_bounds(today_day + timedelta(days=1), tz, user.day_start_hour)[0]

    # (a) the same learning day, even at the last second: not in Ôn.
    set_now(next_start - timedelta(seconds=1))
    same = client.get("/v1/today", headers=headers)
    assert same.status_code == 200
    assert same.json()["review"]["items"] == []

    # (b) the next learning day: in Ôn, with the reason it is there.
    set_now(next_start.astimezone(UTC))
    nxt = client.get("/v1/today", headers=headers).json()
    items = nxt["review"]["items"]
    assert len(items) == 1, nxt["review"]
    assert items[0]["why"] and items[0]["reason"]["kind"] == "new"
