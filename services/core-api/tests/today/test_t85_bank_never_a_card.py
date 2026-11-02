"""T8.5 (US-06 AC8, plan commit 1): a bank or generated question is never a card. Red when a bank
question with no card behind it comes up as a "new" card, or counts as a question in the subject."""

from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_t28_today_api import Space, today

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import Subject
from core_api.domain.learning_day import learning_day
from core_api.repositories.today import TodayRepository
from v2_rows import make_question


def test_bank_question_never_a_card(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject_id = space.subject()
    subject = db_session.get(Subject, subject_id)
    assert subject is not None
    make_question(db_session, user, subject, n=1, source="bank", run_id=None)
    make_question(db_session, user, subject, n=2, source="generated", run_id=None)
    day = learning_day(FROZEN_NOW, ZoneInfo(user.timezone), user.day_start_hour)
    reads = TodayRepository(db_session, user.id)
    assert reads.new_questions(day=day) == []
    assert reads.scheduled_units() == []
    assert reads.has_questions() is False
    body = today(client, headers)
    assert body["review"]["items"] == []
    assert body["state"] == "no_questions"


def test_review_question_is_still_a_card(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    space.question(space.subject())
    body = today(client, headers)
    assert len(body["review"]["items"]) == 1
