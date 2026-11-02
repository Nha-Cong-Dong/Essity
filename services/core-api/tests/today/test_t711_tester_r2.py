"""T7.11 tester round 2 (feature-tester, 02/11): edges found by breaking `repositories/today.py`
and `services/today.py` after migration 0031, where no existing test went red.

US-03 AC4 (only canonical cards are reviewed, each with its own reason), US-02b AC12
(`new_saved_today`), US-02b AC11 (lazy question: one job per card per learning day)."""

import itertools
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_t28_today_api import Space, today
from test_t711_api import canonical

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import KnowledgeUnit, UnitRevision
from core_api.domain.learning_day import day_bounds
from core_api.domain.scheduling.fsrs_adapter import MemoryState, Phase
from core_api.repositories.question import QuestionUnitRepository
from core_api.repositories.review import MemoryStateRepository
from core_api.repositories.today import TodayRepository
from core_api.services.today import enqueue_lazy_questions
from v2_rows import make_question, make_subject, make_unit

_N = itertools.count(20_000)


def _unit(db: Session, unit_id: Any) -> KnowledgeUnit:
    unit = db.get(KnowledgeUnit, unit_id)
    assert unit is not None
    return unit


# US-03 AC4 ("chỉ thẻ chính thức đến hạn"). Red when: a card that was reviewed before and is now
# retired, merged or back to draft still comes as a due question (scheduled_units drops the
# status filter), or its old schedule still feeds the reason of a question (schedules_of).
def test_us03_ac4_a_scheduled_card_that_is_no_longer_canonical_is_not_reviewed(
    db_session: Session,
) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    live, _q = space.question(subject, "TCP")
    canonical(db_session, live)
    space.scheduled(live, due_in_days=-1)
    gone: dict[str, Any] = {}
    for status in ("retired", "merged", "draft"):
        uid, question = space.question(subject, status)
        space.scheduled(uid, due_in_days=-1)
        _unit(db_session, uid).status = status
        gone[status] = question.id
    db_session.flush()
    reads = TodayRepository(db_session, user.id)
    assert [u.unit_id for u in reads.scheduled_units()] == [live]
    assert all(reads.schedules_of(q) == [] for q in gone.values())


# US-02b AC12. Red when: a card saved today and then retired the same day still turns
# `new_saved_today` on, though it will never enter the review on the next learning day.
def test_us02b_ac12_a_card_saved_then_retired_today_is_not_waiting(db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    uid, _q = space.question(space.subject(), "TCP")
    unit = _unit(db_session, uid)
    unit.status, unit.saved_at, unit.saved_learning_day = "retired", FROZEN_NOW, space.today
    db_session.flush()
    assert TodayRepository(db_session, user.id).saved_on(space.today) is False


# US-02b AC11 (T7.9: the lazy question does not retire the old one; a retired question is not
# asked). Red when: a retired review question of a newer revision hides that the active one is
# behind, so the card is asked from its old question and no lazy job is ever made for it.
def test_us02b_ac11_a_retired_newer_question_does_not_hide_staleness(db_session: Session) -> None:
    alice, _ = signed_in(db_session)
    subject = make_subject(db_session, alice)
    unit = make_unit(db_session, alice, subject, status="canonical")
    links = QuestionUnitRepository(db_session, alice.id)
    active = make_question(db_session, alice, subject, n=next(_N), source="review_auto", unit_rev=1)
    retired = make_question(
        db_session, alice, subject, n=next(_N), source="review_auto", unit_rev=3, status="retired"
    )
    for q in (active, retired):
        links.link(q.id, unit.id)
    for rev in range(4):
        db_session.add(
            UnitRevision(user_id=alice.id, unit_id=unit.id, rev=rev, origin="ai", content={})
        )
    db_session.flush()
    assert TodayRepository(db_session, alice.id).stale_rev_units([active.id]) == [unit.id]


# US-03 AC4 ("lý do mỗi thẻ"). Red when: the reason of a review item is read from another card's
# schedule, or from none (shown as "new"), instead of from the units of its own question.
def test_us03_ac4_each_review_item_has_the_reason_of_its_own_card(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    start = day_bounds(space.today, ZoneInfo(user.timezone), user.day_start_hour)[0]
    expected: dict[str, int] = {}
    for title, days_ago in (("TCP", 10), ("UDP", 3), ("IP", 25)):
        uid, question = space.question(subject, title)
        canonical(db_session, uid)
        MemoryStateRepository(db_session, user.id).upsert(
            uid,
            "core",
            MemoryState(
                phase=Phase.REVIEW,
                step=None,
                stability=10.0,
                difficulty=5.0,
                due=start - timedelta(days=1),
                last_review=FROZEN_NOW - timedelta(days=days_ago),
            ),
        )
        expected[str(question.id)] = days_ago
    db_session.flush()
    items = today(client, headers)["review"]["items"]
    got = {i["question_id"]: (i["reason"]["kind"], i["reason"]["days_since_last"]) for i in items}
    assert got == {q: ("review", d) for q, d in expected.items()}


def _failed_lazy_job(db: Session, user_id: Any, unit_id: Any, at: Any) -> None:
    db.execute(
        text(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, args, status)"
            " VALUES ('default', 'regenerate_review_question', CAST(:a AS jsonb), 'failed')"
        ),
        {"a": f'{{"payload": {{"user_id": "{user_id}", "unit_id": "{unit_id}", "lazy": true}}}}'},
    )
    db.execute(
        text(
            "INSERT INTO procrastinate_events (job_id, type, at) SELECT max(id), 'deferred',"
            " :at FROM procrastinate_jobs"
        ),
        {"at": at},
    )


# US-02b AC11, plan D10 (one lazy job per card per learning day, whatever became of it). Red
# when: the window starts at "now" instead of the learning day's start, so a job that failed
# earlier today no longer blocks and every later open of Today enqueues another model call.
def test_us02b_ac11_a_job_that_failed_earlier_today_blocks_a_later_open(
    db_session: Session,
) -> None:
    user, _ = signed_in(db_session)
    subject = make_subject(db_session, user)
    unit = make_unit(db_session, user, subject, status="canonical")
    q = make_question(db_session, user, subject, n=next(_N), source="review_auto", unit_rev=1)
    QuestionUnitRepository(db_session, user.id).link(q.id, unit.id)
    for rev in range(3):
        db_session.add(
            UnitRevision(user_id=user.id, unit_id=unit.id, rev=rev, origin="ai", content={})
        )
    db_session.flush()
    tz = ZoneInfo(user.timezone)
    day_start = day_bounds(FROZEN_NOW.date() + timedelta(days=400), tz, user.day_start_hour)[0]
    _failed_lazy_job(db_session, user.id, unit.id, day_start + timedelta(hours=1))
    db_session.flush()
    reads = TodayRepository(db_session, user.id)
    later = day_start + timedelta(hours=5)
    assert enqueue_lazy_questions(db_session, user, later, reads, [q.id]) == 0
    next_day = day_start + timedelta(days=1, minutes=1)
    assert enqueue_lazy_questions(db_session, user, next_day, reads, [q.id]) == 1
