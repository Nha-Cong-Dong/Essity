"""T7.11: `GET /v1/today` v2 (US-03 AC1/AC3/AC4/AC7/AC8/AC10, US-15 AC1/AC11, US-02b AC11/AC12).

The v1 fields stay as they were; v2 only adds (`unfinished`, `next_study`, `review`, `practice`).
The question chooser is v1's `compose_today`, so what Today shows is what a review session
starts with."""

import re
import uuid
from datetime import timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_t28_today_api import Space, today

from accounts import signed_in
from clock import FROZEN_NOW
from core_api.db.models import KnowledgeUnit, Subject, Submission, UnitRevision
from core_api.domain.learning_day import day_bounds
from core_api.domain.today_v2 import (
    EMPTY_LINKS,
    REASON_ALL_STUDIED,
    REASON_EXAMS_OVER,
    REASON_NO_SYLLABUS,
)
from core_api.repositories.review import ReviewSessionItemRepository
from v2_rows import make_document, make_section, make_study_session, make_unit

V1_FIELDS = {"learning_day", "state", "session", "in_progress", "backlog", "next_day", "subjects"}
BANNED = re.compile(r"\b(phải|cần|kịp|trễ|tồn đọng)\b", re.IGNORECASE)


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in cast(dict[str, Any], value).values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in cast(list[Any], value) for s in strings(v)]
    return []


def canonical(session: Session, unit_id: uuid.UUID) -> KnowledgeUnit:
    unit = session.get(KnowledgeUnit, unit_id)
    assert unit is not None
    unit.status = "canonical"
    session.flush()
    return unit


def subject_row(session: Session, subject_id: uuid.UUID) -> Subject:
    row = session.get(Subject, subject_id)
    assert row is not None
    return row


def add_section(
    session: Session, space: Space, subject_id: uuid.UUID, title: str, **extra: Any
) -> None:
    document = make_document(
        session, space.user, subject_row(session, subject_id), sha=uuid.uuid4().hex * 2
    )
    make_section(session, space.user, document, ord=0, title=title, weight=10, **extra)


# US-03 AC1, T8.5 stable contract. Red when: a part is missing or a v1 field changes.
def test_us03_ac1_today_has_three_parts_and_keeps_the_v1_fields(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit, question = space.question(space.subject())
    space.scheduled(unit, due_in_days=-1)
    body = today(client, headers)
    assert V1_FIELDS <= set(body)
    assert {"unfinished", "next_study", "review", "practice"} <= set(body)
    assert body["practice"] is None  # T8.5 fills it; nothing else moves
    assert body["unfinished"] == []
    item = body["review"]["items"][0]
    assert item["question_id"] == str(question.id) and item["why"]
    assert item["reason"]["kind"] == "review" and 0 <= item["reason"]["retrievability"] <= 1
    assert body["review"]["minutes"] == body["session"]["minutes"]


# US-03 AC3, US-15 AC1. Red when: more than two subjects, or a suggestion has no reason.
def test_us03_ac3_next_study_is_the_top_two_with_a_reason(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    for name, days in (("A", 5), ("B", 30), ("C", 60)):
        subject = space.subject(name, exam_in_days=days)
        add_section(db_session, space, subject, f"Mục {name}")
    body = today(client, headers)["next_study"]
    assert len(body["items"]) == 2 and body["empty_reason"] is None and body["links"] == []
    assert body["items"][0]["subject_name"] == "A"
    assert all(i["reason"] and i["section_title"] for i in body["items"])


# US-15 AC11 (three cases). Red when: the line is missing or the three links are not offered.
@pytest.mark.parametrize("case", ["exams_over", "no_syllabus", "all_studied"])
def test_us15_ac11_next_study_empty_gives_one_neutral_line_and_three_links(
    client: TestClient, db_session: Session, case: str
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject(exam_in_days=-3 if case == "exams_over" else 30)
    if case == "all_studied":
        add_section(db_session, space, subject, "Mục 1", studied_weight=10)
    expected = {
        "exams_over": REASON_EXAMS_OVER,
        "no_syllabus": REASON_NO_SYLLABUS,
        "all_studied": REASON_ALL_STUDIED,
    }[case]
    body = today(client, headers)["next_study"]
    assert body["items"] == [] and body["empty_reason"] == expected
    assert tuple(body["links"]) == EMPTY_LINKS


# US-03 AC4. Red when: a draft or retired card is asked, or the v1 caps change.
def test_us03_ac4_review_has_only_live_due_cards_and_the_v1_caps(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    for n in range(30):
        unit, _ = space.question(subject, f"c{n}")
        space.scheduled(unit, due_in_days=-1)
        canonical(db_session, unit)
    for status in ("draft", "retired"):
        unit, _ = space.question(subject, status)
        space.scheduled(unit, due_in_days=-1)
        stale = db_session.get(KnowledgeUnit, unit)
        assert stale is not None
        stale.status = status
    db_session.flush()
    review = today(client, headers)["review"]
    assert len(review["items"]) == 20 and review["minutes"] == 30
    assert all(i["why"] and i["reason"] for i in review["items"])


# US-02b AC12. Red when: a card saved today is asked today, or the 04:00 boundary is off.
def test_us02b_ac12_a_card_saved_today_enters_from_the_next_learning_day(
    client: TestClient, db_session: Session, set_now: Any
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit, _ = space.question(space.subject(), "TCP")
    saved = canonical(db_session, unit)
    saved.saved_at, saved.saved_learning_day = FROZEN_NOW, space.today
    db_session.flush()
    tz = ZoneInfo(user.timezone)
    next_start = day_bounds(space.today + timedelta(days=1), tz, user.day_start_hour)[0]
    set_now(next_start - timedelta(seconds=1))  # 03:59 is still the same learning day
    assert today(client, headers)["review"]["items"] == []
    # Today and the session it starts agree (plan P3): the card is not in the session either.
    assert client.post("/v1/review-sessions", json={}, headers=headers).status_code == 409
    set_now(next_start)  # 04:00
    assert len(today(client, headers)["review"]["items"]) == 1


# US-03 AC7. Red when: nothing due gives no next day.
def test_us03_ac7_nothing_due_shows_the_next_due_day(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit, _ = space.question(space.subject())
    space.scheduled(unit, due_in_days=3)
    review = today(client, headers)["review"]
    assert review["items"] == []
    assert review["next_due_day"] == (space.today + timedelta(days=3)).isoformat()


# US-03 AC1 (unfinished). Red when: done submissions show, or a count is exposed.
def test_us03_ac1_unfinished_lines_for_drafts_and_pending_ai(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject_id = space.subject("Mạng máy tính")
    subject = subject_row(db_session, subject_id)
    drafts = make_study_session(db_session, user, subject)
    make_unit(db_session, user, subject, status="draft", session_id=drafts.id)
    waiting = make_study_session(db_session, user, subject)
    db_session.add(Submission(user_id=user.id, session_id=waiting.id, status="pending_ai"))
    done = make_study_session(db_session, user, subject)
    db_session.add(
        Submission(user_id=user.id, session_id=done.id, status="done", finished_at=FROZEN_NOW)
    )
    db_session.flush()
    body = today(client, headers)
    lines = body["unfinished"]
    assert {line["session_id"] for line in lines} == {str(drafts.id), str(waiting.id)}
    assert all(line["line"] and line["subject_id"] == str(subject_id) for line in lines)
    assert "backlog_total" not in body


# US-03 AC8, plan P5. Red when: the preview differs from the session it starts.
def test_us03_ac8_subject_filter_matches_the_session_it_starts(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    a, b = space.subject("A"), space.subject("B")
    for subject, tag in ((a, "a"), (b, "b")):
        for n in range(30):
            unit, _ = space.question(subject, f"{tag}{n}")
            space.scheduled(unit, due_in_days=-1)
    shown = client.get(f"/v1/today?subject_id={a}", headers=headers)
    assert shown.status_code == 200, shown.text
    ids = [i["question_id"] for i in shown.json()["review"]["items"]]
    assert len(ids) == 20
    started = client.post("/v1/review-sessions", json={"subject_id": str(a)}, headers=headers)
    assert started.status_code == 201, started.text
    steps = ReviewSessionItemRepository(db_session, user.id).of_session(
        uuid.UUID(started.json()["id"])
    )
    assert sorted(ids) == sorted(str(step.question_id) for step in steps)


def test_us03_ac8_a_subject_of_someone_else_is_not_found(
    client: TestClient, db_session: Session
) -> None:
    alice, _ = signed_in(db_session)
    _, bob_headers = signed_in(db_session)
    theirs = Space(db_session, alice).subject()
    assert client.get(f"/v1/today?subject_id={theirs}", headers=bob_headers).status_code == 404
    assert (
        client.get(f"/v1/today?subject_id={uuid.uuid4()}", headers=bob_headers).status_code == 404
    )


# US-03 AC5 (the wording is the screen's): the backlog carries the unit count.
def test_us03_ac5_backlog_carries_the_unit_count(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject(exam_in_days=5)
    for n in range(120):
        unit, _ = space.question(subject, f"u{n}")
        space.scheduled(unit, due_in_days=-1)
    backlog = today(client, headers)["backlog"]
    assert (backlog["sessions"], backlog["days"], backlog["units"]) == (6, 5, 120)


# US-03 AC10, US-15 AC4. Red when: pressure wording appears anywhere in the answer.
def test_us03_ac10_no_pressure_wording_anywhere(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject(exam_in_days=5)
    add_section(db_session, space, subject, "Mục 1")
    for n in range(60):
        unit, _ = space.question(subject, f"u{n}")
        space.scheduled(unit, due_in_days=-1)
    found = [s for s in strings(today(client, headers)) if BANNED.search(s)]
    assert found == []


# ADR-0013/14. Red when: another user's data reaches the answer, or an unverified user gets one.
def test_adr0014_unverified_user_gets_403(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session, verified=False)
    assert client.get("/v1/today", headers=headers).status_code == 403


def test_t711_isolation_user_b_sees_nothing_of_user_a(
    client: TestClient, db_session: Session
) -> None:
    alice, _ = signed_in(db_session)
    _, bob_headers = signed_in(db_session)
    space = Space(db_session, alice)
    unit, _ = space.question(space.subject())
    space.scheduled(unit, due_in_days=-1)
    body = today(client, bob_headers)
    assert body["review"]["items"] == [] and body["unfinished"] == []
    assert body["next_study"]["items"] == []


# --- the lazy review question hook (US-02b AC11, T7.9) ---------------------------------------


def _jobs(session: Session, unit_id: uuid.UUID) -> list[Any]:
    return list(
        session.execute(
            text(
                "SELECT args->'payload' FROM procrastinate_jobs"
                " WHERE task_name = 'regenerate_review_question'"
                " AND args->'payload'->>'unit_id' = :u"
            ),
            {"u": str(unit_id)},
        ).scalars()
    )


def _stale_card(
    session: Session, space: Space, rev_question: int = 1, rev_unit: int = 2
) -> uuid.UUID:
    unit, question = space.question(space.subject(), "TCP")
    canonical(session, unit)
    question.source, question.unit_rev = "review_auto", rev_question
    for rev in range(rev_unit + 1):
        session.add(
            UnitRevision(user_id=space.user.id, unit_id=unit, rev=rev, origin="ai", content={})
        )
    space.scheduled(unit, due_in_days=-1)
    session.flush()
    return unit


def test_us02b_ac11_a_due_card_with_a_newer_revision_enqueues_one_lazy_job(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    unit = _stale_card(db_session, Space(db_session, user))
    today(client, headers)
    jobs = _jobs(db_session, unit)
    assert len(jobs) == 1 and jobs[0]["lazy"] is True and jobs[0]["user_id"] == str(user.id)
    today(client, headers)  # a refetch makes no second job
    assert len(_jobs(db_session, unit)) == 1


def test_us02b_ac11_a_current_question_enqueues_nothing(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    unit = _stale_card(db_session, Space(db_session, user), rev_question=2, rev_unit=2)
    today(client, headers)
    assert _jobs(db_session, unit) == []


def test_us02b_ac11_only_cards_in_todays_review_enqueue(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    unit = _stale_card(db_session, space)
    other_unit, other_question = space.question(space.subject("B"), "UDP")
    canonical(db_session, other_unit)
    other_question.source, other_question.unit_rev = "review_auto", 1
    space.scheduled(other_unit, due_in_days=9)  # not due: not in review
    db_session.add(
        UnitRevision(user_id=user.id, unit_id=other_unit, rev=5, origin="ai", content={})
    )
    db_session.flush()
    today(client, headers)
    assert len(_jobs(db_session, unit)) == 1 and _jobs(db_session, other_unit) == []


def test_us02b_ac11_a_failing_queue_keeps_the_answer(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, headers = signed_in(db_session)
    unit = _stale_card(db_session, Space(db_session, user))

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("queue down")

    monkeypatch.setattr("core_api.services.today.enqueue_review_question", boom)
    body = today(client, headers)
    assert len(body["review"]["items"]) == 1 and _jobs(db_session, unit) == []


def test_us02b_ac11_a_job_of_another_user_does_not_block_mine(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    other, _ = signed_in(db_session)
    unit = _stale_card(db_session, Space(db_session, user))
    db_session.execute(
        text(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, args, status)"
            " VALUES ('default', 'regenerate_review_question', CAST(:a AS jsonb), 'todo')"
        ),
        {"a": f'{{"payload": {{"user_id": "{other.id}", "unit_id": "{unit}", "lazy": true}}}}'},
    )
    today(client, headers)
    mine = [a for a in _jobs(db_session, unit) if a["user_id"] == str(user.id)]
    assert len(mine) == 1
