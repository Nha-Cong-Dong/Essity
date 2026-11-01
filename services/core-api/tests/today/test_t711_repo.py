"""T7.11 C2: what `TodayRepository` reads for Today v2 and the review session builder.

Canonical cards (saved by T7.8) are live next to the legacy `active` ones; a card saved today
enters from the next learning day (US-02b AC12); of two review questions of one card the newest
revision is asked (T7.9 lazy regeneration)."""

from datetime import timedelta

from sqlalchemy.orm import Session
from test_t28_today_api import Space

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import KnowledgeUnit, Question
from core_api.repositories.question import QuestionUnitRepository
from core_api.repositories.today import TodayRepository


def _unit(db: Session, unit_id: object) -> KnowledgeUnit:
    unit = db.get(KnowledgeUnit, unit_id)
    assert unit is not None
    return unit


def test_us03_ac4_canonical_card_is_live_in_every_read(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    due_unit, _q = space.question(subject, "TCP")
    new_unit, new_q = space.question(subject, "UDP")
    space.scheduled(due_unit, due_in_days=-1)
    for uid in (due_unit, new_unit):
        _unit(db_session, uid).status = "canonical"
    db_session.flush()
    reads = TodayRepository(db_session, user.id)
    assert {u.unit_id for u in reads.scheduled_units()} == {due_unit}
    assert [q.question_id for q in reads.new_questions(day=space.today)] == [new_q.id]
    assert reads.unasked_by_subject(day=space.today) == {subject: 1}


def test_us03_ac4_draft_retired_and_split_units_are_not_asked(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    for status in ("draft", "retired"):
        uid, _q = space.question(subject, status)
        _unit(db_session, uid).status = status
    db_session.flush()
    reads = TodayRepository(db_session, user.id)
    assert reads.new_questions(day=space.today) == []
    assert reads.unasked_by_subject(day=space.today) == {}


def test_us02b_ac12_card_saved_today_enters_from_the_next_learning_day(
    db_session: Session,
) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    uid, q = space.question(subject, "TCP")
    unit = _unit(db_session, uid)
    unit.status, unit.saved_at, unit.saved_learning_day = "canonical", FROZEN_NOW, space.today
    db_session.flush()
    reads = TodayRepository(db_session, user.id)
    assert reads.new_questions(day=space.today) == []
    assert reads.unasked_by_subject(day=space.today) == {}
    tomorrow = space.today + timedelta(days=1)
    assert [x.question_id for x in reads.new_questions(day=tomorrow)] == [q.id]
    assert reads.unasked_by_subject(day=tomorrow) == {subject: 1}


def test_t79_the_newest_revision_question_is_the_one_asked(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    uid, old = space.question(subject, "TCP")
    space.scheduled(uid, due_in_days=-1)
    newer = Question(
        user_id=user.id,
        subject_id=subject,
        level=1,
        prompt="TCP mới?",
        reference_answer="a",
        content_hash="f" * 64,
        run_id=old.run_id,
        source="review_auto",
        unit_rev=2,
        created_at=old.created_at + timedelta(days=1),  # later, so the old rule picked `old`
    )
    db_session.add(newer)
    db_session.flush()
    QuestionUnitRepository(db_session, user.id).link(newer.id, uid)
    db_session.flush()
    due = TodayRepository(db_session, user.id).scheduled_units()
    assert [u.question_id for u in due] == [newer.id]


def test_t79_a_never_asked_card_with_two_questions_is_new_once(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    uid, old = space.question(subject, "TCP")
    newer = Question(
        user_id=user.id,
        subject_id=subject,
        level=1,
        prompt="TCP mới?",
        reference_answer="a",
        content_hash="e" * 64,
        run_id=old.run_id,
        source="review_auto",
        unit_rev=3,
        created_at=old.created_at - timedelta(days=1),
    )
    db_session.add(newer)
    db_session.flush()
    QuestionUnitRepository(db_session, user.id).link(newer.id, uid)
    db_session.flush()
    fresh = TodayRepository(db_session, user.id).new_questions(day=space.today)
    assert [q.question_id for q in fresh] == [newer.id]
