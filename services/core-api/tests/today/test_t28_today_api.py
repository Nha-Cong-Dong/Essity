"""T2.8: `GET /v1/today` (US-03 AC1, AC3–AC6, ARCH §5.3). Read-only; the composition itself is
T2.7's (`domain/today.py`), tested there. Here: what the route reads, and what it answers."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import Question, User
from core_api.domain.learning_day import day_bounds, learning_day
from core_api.domain.scheduling.fsrs_adapter import MemoryState, Phase
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import MemoryStateRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import AnchorRepository, KnowledgeUnitRepository

RUN = uuid.uuid4()


class Space:
    """One user's subjects, units and questions, written through the repositories."""

    def __init__(self, session: Session, user: User) -> None:
        self.session, self.user = session, user
        self.today = learning_day(FROZEN_NOW, ZoneInfo(user.timezone), user.day_start_hour)

    def subject(self, name: str = "Mạng máy tính", exam_in_days: int = 60) -> uuid.UUID:
        subject, _ = SubjectRepository(self.session, self.user.id).create_with_exam(
            name, self.today + timedelta(days=exam_in_days)
        )
        return subject.id

    def question(self, subject_id: uuid.UUID, title: str = "TCP") -> tuple[uuid.UUID, Question]:
        unit = KnowledgeUnitRepository(self.session, self.user.id).create(
            subject_id, title=title, summary="s", kind="concept", run_id=RUN
        )
        question = QuestionRepository(self.session, self.user.id).add_idempotent(
            subject_id, level=1, prompt=f"{title}?", reference_answer="a", run_id=RUN
        )
        QuestionUnitRepository(self.session, self.user.id).link(question.id, unit.id)
        # Grading needs at least one source per unit (T2.13, US-05 AC8).
        AnchorRepository(self.session, self.user.id).create(
            unit.id,
            source="document",
            quote_text=f"{title} là một khái niệm của môn.",
            page_no=1,
            run_id=RUN,
        )
        self.session.flush()
        return unit.id, question

    def scheduled(self, unit_id: uuid.UUID, due_in_days: int) -> None:
        start = day_bounds(self.today, ZoneInfo(self.user.timezone), self.user.day_start_hour)[0]
        MemoryStateRepository(self.session, self.user.id).upsert(
            unit_id,
            "core",
            MemoryState(
                phase=Phase.REVIEW,
                step=None,
                stability=10.0,
                difficulty=5.0,
                due=start + timedelta(days=due_in_days),
                last_review=FROZEN_NOW - timedelta(days=10),
            ),
        )
        self.session.flush()


def today(client: TestClient, headers: dict[str, str]) -> Any:
    response = client.get("/v1/today", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_t28_no_subjects(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    body = today(client, headers)
    assert body["state"] == "no_subjects"
    assert body["session"] is None and body["subjects"] == []


def test_t28_subjects_without_questions(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    Space(db_session, user).subject()
    assert today(client, headers)["state"] == "no_questions"


# US-03 AC1. Red when: a field the screen needs is missing.
def test_us03_ac1_today_has_count_minutes_subjects(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    mmt = space.subject("Mạng máy tính")
    space.question(mmt, "TCP")
    space.question(mmt, "UDP")
    body = today(client, headers)
    assert body["state"] == "ready"
    assert body["learning_day"] == space.today.isoformat()
    assert body["session"] == {
        "question_count": 2,
        "minutes": 3,
        "subjects": [{"id": str(mmt), "name": "Mạng máy tính"}],
    }
    assert body["subjects"][0]["name"] == "Mạng máy tính"


# US-03 AC3 through the route. Red when: due units are not read, or are read with the wrong
# question.
def test_us03_ac3_a_due_unit_and_a_new_question_both_come(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    mmt = space.subject()
    due_unit, _ = space.question(mmt, "TCP")
    space.scheduled(due_unit, due_in_days=-1)
    space.question(mmt, "UDP")
    assert today(client, headers)["session"]["question_count"] == 2


# US-03 AC6. Red when: nothing due gives an empty answer with no next day.
def test_us03_ac6_rested_has_next_day(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit, _ = space.question(space.subject())
    space.scheduled(unit, due_in_days=3)
    body = today(client, headers)
    assert body["state"] == "rested"
    assert body["session"] is None
    assert body["next_day"] == (space.today + timedelta(days=3)).isoformat()


# US-03 AC5 through the route: structured, with the subject's name for the screen's sentence.
def test_us03_ac5_backlog_is_structured(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    mmt = space.subject("Mạng máy tính", exam_in_days=5)
    for n in range(120):
        unit, _ = space.question(mmt, f"u{n}")
        space.scheduled(unit, due_in_days=-1)
    body = today(client, headers)
    assert body["session"]["question_count"] == 20
    assert body["backlog"] == {
        "subject_id": str(mmt),
        "subject_name": "Mạng máy tính",
        "sessions": 6,
        "days": 5,
    }


# T2.8 "Xong khi": a deleted subject is left out. Red when: the soft delete is not filtered.
def test_t28_deleted_subject_excluded(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    kept, gone = space.subject("Giữ"), space.subject("Xóa")
    space.question(kept, "TCP")
    unit, _ = space.question(gone, "UDP")
    space.scheduled(unit, due_in_days=-1)
    SubjectRepository(db_session, user.id).soft_delete(gone, FROZEN_NOW)
    body = today(client, headers)
    assert body["session"]["question_count"] == 1
    assert [s["id"] for s in body["subjects"]] == [str(kept)]


# Red when: a retired question is still asked.
def test_t28_retired_questions_are_not_asked(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    _, question = space.question(space.subject())
    question.status = "retired"
    db_session.flush()
    assert today(client, headers)["state"] == "no_questions"


def test_t28_all_exams_over(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit, _ = space.question(space.subject(exam_in_days=-2))
    space.scheduled(unit, due_in_days=4)
    assert today(client, headers)["state"] == "all_exams_over"


# ADR-0001. Red when: one user's subjects or questions reach another's /v1/today.
def test_t28_today_isolated_two_users(client: TestClient, db_session: Session) -> None:
    alice, _ = signed_in(db_session)
    _, bob_headers = signed_in(db_session)
    space = Space(db_session, alice)
    unit, _ = space.question(space.subject())
    space.scheduled(unit, due_in_days=-1)
    body = today(client, bob_headers)
    assert body["state"] == "no_subjects" and body["subjects"] == []


def test_t28_learning_day_follows_the_clock(
    client: TestClient, db_session: Session, set_now: Any
) -> None:
    _, headers = signed_in(db_session)
    set_now(datetime(2026, 10, 24, 20, 59, tzinfo=FROZEN_NOW.tzinfo))  # 03:59 on the 25th, HCM
    assert today(client, headers)["learning_day"] == date(2026, 10, 24).isoformat()
    set_now(datetime(2026, 10, 24, 21, 0, tzinfo=FROZEN_NOW.tzinfo))  # 04:00
    assert today(client, headers)["learning_day"] == date(2026, 10, 25).isoformat()
