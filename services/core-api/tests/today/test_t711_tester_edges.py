"""T7.11 tester: edges the branch tests leave open (feature-tester, 02/11).

US-02b AC11 (lazy question: one job per card per day, a broken enqueue never breaks Today),
US-02b AC12 (`new_saved_today` follows the learning day), US-03 AC8 (the subject filter also
narrows new questions, as the session start does)."""

import itertools
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_t28_today_api import Space, today
from test_t711_api import _jobs, _stale_card, canonical  # pyright: ignore[reportPrivateUsage]

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import Subject, UnitRevision
from core_api.domain.learning_day import day_bounds
from core_api.repositories.question import QuestionUnitRepository
from core_api.repositories.review import ReviewSessionItemRepository
from core_api.repositories.today import TodayRepository
from v2_rows import make_question, make_study_session, make_subject, make_unit

_N = itertools.count(10_000)


# US-02b AC12. Red when: `new_saved_today` ignores the learning day (always true/false, or
# compares with the calendar date instead of the 04:00 boundary).
def test_us02b_ac12_new_saved_today_follows_the_learning_day(
    client: TestClient, db_session: Session, set_now: Any
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit, _ = space.question(space.subject(), "TCP")
    assert today(client, headers)["review"]["new_saved_today"] is False
    saved = canonical(db_session, unit)
    saved.saved_at, saved.saved_learning_day = FROZEN_NOW, space.today
    db_session.flush()
    assert today(client, headers)["review"]["new_saved_today"] is True
    tz = ZoneInfo(user.timezone)
    next_start = day_bounds(space.today + timedelta(days=1), tz, user.day_start_hour)[0]
    set_now(next_start - timedelta(seconds=1))
    assert today(client, headers)["review"]["new_saved_today"] is True
    set_now(next_start)
    assert today(client, headers)["review"]["new_saved_today"] is False


# US-02b AC12, ADR-0013. Red when: a card another user saved today, or one of a deleted subject,
# turns my `new_saved_today` on.
def test_us02b_ac12_new_saved_today_counts_only_my_visible_subjects(
    client: TestClient, db_session: Session
) -> None:
    alice, alice_headers = signed_in(db_session)
    bob, _ = signed_in(db_session)
    theirs = Space(db_session, bob)
    unit, _ = theirs.question(theirs.subject(), "TCP")
    saved = canonical(db_session, unit)
    saved.saved_at, saved.saved_learning_day = FROZEN_NOW, theirs.today
    mine = Space(db_session, alice)
    gone_subject = mine.subject("Đã xóa")
    gone_unit, _ = mine.question(gone_subject, "UDP")
    gone = canonical(db_session, gone_unit)
    gone.saved_at, gone.saved_learning_day = FROZEN_NOW, mine.today
    row = db_session.get(Subject, gone_subject)
    assert row is not None
    row.deleted_at = FROZEN_NOW
    db_session.flush()
    assert today(client, alice_headers)["review"]["new_saved_today"] is False


# US-03 AC10 ("tính lại từ trạng thái hiện tại mỗi lần mở"). Red when: a second open within the
# same learning day answers from what the first one composed (a cached plan) instead of the data.
def test_us03_ac10_two_opens_in_a_row_recompute_from_the_data(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    first, _ = space.question(subject, "TCP")
    space.scheduled(first, due_in_days=-1)
    before = today(client, headers)
    assert len(before["review"]["items"]) == 1
    second, q2 = space.question(subject, "UDP")
    space.scheduled(second, due_in_days=-2)
    space.scheduled(first, due_in_days=4)  # answered elsewhere: no longer due
    after = today(client, headers)
    assert [i["question_id"] for i in after["review"]["items"]] == [str(q2.id)]


# US-03 AC8, plan D14. Red when: never-asked questions of another subject reach the preview of
# "Ôn riêng môn này", so it differs from the session `POST {"subject_id"}` starts.
def test_us03_ac8_subject_filter_narrows_new_questions_like_the_session(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    a, b = space.subject("A", exam_in_days=40), space.subject("B", exam_in_days=10)
    for subject, tag in ((a, "a"), (b, "b")):
        for n in range(12):
            space.question(subject, f"{tag}{n}")  # never asked: new questions only
    shown = client.get(f"/v1/today?subject_id={a}", headers=headers)
    assert shown.status_code == 200, shown.text
    body = shown.json()
    items = body["review"]["items"]
    assert items and {i["subject_id"] for i in items} == {str(a)}
    assert [s["id"] for s in body["session"]["subjects"]] == [str(a)]
    started = client.post("/v1/review-sessions", json={"subject_id": str(a)}, headers=headers)
    assert started.status_code == 201, started.text
    steps = ReviewSessionItemRepository(db_session, user.id).of_session(
        uuid.UUID(started.json()["id"])
    )
    assert sorted(i["question_id"] for i in items) == sorted(str(s.question_id) for s in steps)


# US-02b AC11, plan risk "GET có ghi". Red when: the enqueue is not inside a savepoint, so a
# database error in it aborts the request's transaction and Today fails.
def test_us02b_ac11_a_database_error_while_enqueueing_keeps_the_answer(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, headers = signed_in(db_session)
    unit = _stale_card(db_session, Space(db_session, user))

    def broken(session: Session, *args: object, **kwargs: object) -> None:
        session.execute(text("SELECT 1 / 0"))  # the transaction sees a real SQL error

    monkeypatch.setattr("core_api.services.today.enqueue_review_question", broken)
    body = today(client, headers)
    assert len(body["review"]["items"]) == 1
    assert _jobs(db_session, unit) == []  # the session is still usable afterwards


def _card(db: Session, user: Any, subject: Any, *question_revs: int) -> tuple[Any, list[Any]]:
    unit = make_unit(db, user, subject, status="canonical")
    questions: list[Any] = []
    for rev in question_revs:
        q = make_question(db, user, subject, n=next(_N), source="review_auto", unit_rev=rev)
        QuestionUnitRepository(db, user.id).link(q.id, unit.id)
        questions.append(q)
    return unit, questions


def _revisions(db: Session, user: Any, unit: Any, top: int) -> None:
    for rev in range(top + 1):
        db.add(UnitRevision(user_id=user.id, unit_id=unit.id, rev=rev, origin="ai", content={}))
    db.flush()


# US-02b AC11 (T7.9: the lazy question does not retire the old one). Red when: the oldest of two
# review questions decides, so a card already regenerated is enqueued again on every new day.
def test_us02b_ac11_with_two_review_questions_the_newest_decides_staleness(
    db_session: Session,
) -> None:
    alice, _ = signed_in(db_session)
    subject = make_subject(db_session, alice)
    current, (_old, new) = _card(db_session, alice, subject, 1, 2)
    _revisions(db_session, alice, current, 2)
    behind, (_b_old, b_new) = _card(db_session, alice, subject, 1, 2)
    _revisions(db_session, alice, behind, 3)
    got = TodayRepository(db_session, alice.id).stale_rev_units([new.id, b_new.id])
    assert got == [behind.id]


def _job(db: Session, user_id: Any, unit_id: Any, status: str, task: str) -> None:
    db.execute(
        text(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, args, status)"
            " VALUES ('default', :t, CAST(:a AS jsonb), CAST(:s AS procrastinate_job_status))"
        ),
        {
            "t": task,
            "a": f'{{"payload": {{"user_id": "{user_id}", "unit_id": "{unit_id}", "lazy": true}}}}',
            "s": status,
        },
    )


# US-02b AC11, plan D10. Red when: a job a worker is running (`doing`) does not block a second
# one, or a job of another kind for the same card blocks the lazy question.
def test_us02b_ac11_a_running_job_blocks_and_another_kind_does_not(db_session: Session) -> None:
    alice, _ = signed_in(db_session)
    subject = make_subject(db_session, alice)
    running, _q1 = _card(db_session, alice, subject, 1)
    other_kind, _q2 = _card(db_session, alice, subject, 1)
    _job(db_session, alice.id, running.id, "doing", "regenerate_review_question")
    _job(db_session, alice.id, other_kind.id, "todo", "send_email")
    db_session.flush()
    since = datetime(2099, 1, 1, tzinfo=UTC)  # no event counts: only the status decides
    got = TodayRepository(db_session, alice.id).lazy_jobs_since([running.id, other_kind.id], since)
    assert got == {running.id}


# US-03 AC1 (việc dở). Red when: a session whose cards are all saved, or only retired, still
# shows as unfinished: only draft cards (or a submission waiting for the AI) make it unfinished.
def test_us03_ac1_a_session_with_only_saved_or_retired_cards_is_not_unfinished(
    db_session: Session,
) -> None:
    alice, _ = signed_in(db_session)
    subject = make_subject(db_session, alice)
    saved = make_study_session(db_session, alice, subject)
    make_unit(db_session, alice, subject, status="canonical", session_id=saved.id)
    make_unit(db_session, alice, subject, status="retired", session_id=saved.id)
    assert TodayRepository(db_session, alice.id).unfinished_sessions() == []
