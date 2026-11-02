"""T5.R: today and review sessions offer level-1 questions only. Levels 2 and 3 (apply, deep
apply) are optional practice made on demand later; a question of those levels that is already
in the database never reaches today, whether its unit is due or new."""

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_t28_today_api import RUN, Space, today

from accounts import signed_in
from core_api.db.models import Question
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.today import TodayRepository

DAY = date(2026, 11, 2)  # no card here is saved, so the day does not matter


def add_higher(
    space: Space, subject_id: uuid.UUID, level: int, prompt: str, *units: uuid.UUID
) -> None:
    question = QuestionRepository(space.session, space.user.id).add_idempotent(
        subject_id, level=level, prompt=prompt, reference_answer="a", run_id=RUN
    )
    for unit in units:
        QuestionUnitRepository(space.session, space.user.id).link(question.id, unit)
    space.session.flush()


def test_t5r_a_due_unit_is_asked_its_level_1_question_even_when_a_higher_one_is_older(
    db_session: Session,
) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    unit, level_one = space.question(subject, "TCP")
    space.scheduled(unit, due_in_days=-1)
    add_higher(space, subject, 2, "Áp dụng TCP?", unit)
    add_higher(space, subject, 3, "Nối TCP?", unit)

    due = TodayRepository(db_session, user.id).scheduled_units()
    assert [(u.unit_id, u.question_id) for u in due] == [(unit, level_one.id)]


def test_t5r_a_unit_with_only_higher_questions_is_not_in_today(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    unit, _ = space.question(subject, "TCP")
    other, _ = space.question(subject, "UDP")
    space.scheduled(unit, due_in_days=-1)
    space.scheduled(other, due_in_days=-1)
    # retire UDP's level-1 question; leave it only a level-2 one
    for q in db_session.query(Question).filter(Question.prompt == "UDP?"):
        q.status = "retired"
    add_higher(space, subject, 2, "Áp dụng UDP?", other)

    due = TodayRepository(db_session, user.id).scheduled_units()
    assert {u.unit_id for u in due} == {unit}


def test_t5r_higher_questions_on_a_new_unit_are_not_new_questions(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    unit, level_one = space.question(subject, "TCP")  # never scheduled: new
    add_higher(space, subject, 2, "Áp dụng TCP?", unit)
    add_higher(space, subject, 3, "Nối TCP?", unit)

    fresh = TodayRepository(db_session, user.id).new_questions(day=DAY)
    assert [q.question_id for q in fresh] == [level_one.id]


def test_t5r_a_subject_with_only_higher_questions_has_no_questions(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    add_higher(space, subject, 2, "Áp dụng?")
    assert TodayRepository(db_session, user.id).has_questions() is False
    assert today(client, headers)["session"] is None
