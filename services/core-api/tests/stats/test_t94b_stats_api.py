"""T9.4b (US-10): `GET /v1/stats` and `GET /v1/export.csv` over the real tables. The pure rules are
in tests/domain/test_stats.py; here the reads, the API shape, isolation and the unverified user."""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core_api.db.models import (
    QuestionSection,
    Subject,
    UnitRevision,
    UnitSection,
    User,
)
from core_api.domain.scheduling.fsrs_adapter import MemoryState, Phase
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.review import (
    AttemptRepository,
    MemoryStateRepository,
    ReviewSessionRepository,
)
from practice_rows import Practice
from stats.conftest import NOW
from v2_rows import make_document, make_question, make_section, make_subject, make_type, make_unit


def headers_of(session: Session, user: User) -> dict[str, str]:
    user.email_verified_at = NOW
    token, _ = AuthSessionRepository(session).create(user.id, datetime.now(UTC))
    session.flush()
    return {"Authorization": f"Bearer {token}"}


def stats(client: TestClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    response = client.get("/v1/stats", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def one(body: dict[str, Any], subject: Subject) -> dict[str, Any]:
    return next(s for s in body["subjects"] if s["id"] == str(subject.id))


def schedule(session: Session, user: User, unit_id: uuid.UUID, stability: float) -> None:
    MemoryStateRepository(session, user.id).upsert(
        unit_id,
        "core",
        MemoryState(
            phase=Phase.REVIEW,
            step=None,
            stability=stability,
            difficulty=5.0,
            due=NOW + timedelta(days=1),
            last_review=NOW - timedelta(days=1),
        ),
    )


def answer(
    session: Session,
    user: User,
    question_id: uuid.UUID,
    at: datetime,
    *,
    started: datetime | None = None,
    end: bool = True,
) -> None:
    """A submitted attempt in a sitting of its own, left open when `end` is False."""
    sessions = ReviewSessionRepository(session, user.id)
    began = started or at
    sitting = sessions.start(began.date(), began)
    attempts = AttemptRepository(session, user.id)
    attempt = attempts.create_draft(sitting.id, question_id)
    attempts.submit(attempt.id, at)
    if end:
        sessions.end(sitting.id, at, reason="completed")


def save_card(
    session: Session, user: User, subject: Subject, at: datetime, section_id: uuid.UUID | None
) -> None:
    unit = make_unit(session, user, subject, status="canonical")
    session.add(
        UnitRevision(
            user_id=user.id, unit_id=unit.id, rev=1, origin="user", content={}, created_at=at
        )
    )
    if section_id is not None:
        session.add(
            UnitSection(
                user_id=user.id, subject_id=subject.id, unit_id=unit.id, section_id=section_id
            )
        )
    session.flush()


# US-10 AC1, AC3: % syllabus by leaf, pages reported per unit, an excluded leaf left out.
def test_syllabus_percent_by_leaf_with_units_apart(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: parents count as leaves, excluded leaves count, or page and slide weights add up.
    alice, _ = two_users
    headers = headers_of(db_session, alice)
    subject = make_subject(db_session, alice)
    doc = make_document(db_session, alice, subject)
    parent = make_section(db_session, alice, doc, title="Chương", weight=15)
    make_section(db_session, alice, doc, parent_id=parent.id, weight=10, studied_weight=10)
    make_section(db_session, alice, doc, parent_id=parent.id, weight=5)
    make_section(db_session, alice, doc, unit="slide", weight=3, studied_weight=3, title="S")
    make_section(db_session, alice, doc, weight=9, excluded=True, title="Không thi")
    body = one(stats(client, headers), subject)
    syllabus = body["syllabus"]
    assert (syllabus["leaves"], syllabus["studied_leaves"], syllabus["percent"]) == (3, 2, 67)
    by_unit = {u["unit"]: (u["studied"], u["total"]) for u in syllabus["by_unit"]}
    assert by_unit == {"page": (10.0, 15.0), "slide": (3.0, 3.0)}
    assert body["days_left"] == 62


# US-10 AC2, AC10: share of cards with recall >= 90%; skipped and unscheduled cards leave it.
def test_retention_share_and_skipped_cards_excluded(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: a skipped, unscheduled or draft card is in the sample.
    alice, _ = two_users
    headers = headers_of(db_session, alice)
    subject = make_subject(db_session, alice)
    solid = make_unit(db_session, alice, subject, status="canonical")
    weak = make_unit(db_session, alice, subject, status="canonical")
    skipped = make_unit(db_session, alice, subject, status="canonical", skipped_at=NOW)
    make_unit(db_session, alice, subject, status="canonical")  # never asked
    draft = make_unit(db_session, alice, subject, status="draft")
    schedule(db_session, alice, solid.id, 1000)
    schedule(db_session, alice, weak.id, 0.1)
    schedule(db_session, alice, skipped.id, 0.1)
    schedule(db_session, alice, draft.id, 0.1)
    assert one(stats(client, headers), subject)["retention"] == 0.5
    empty = make_subject(db_session, alice, "Trống")
    assert one(stats(client, headers), empty)["retention"] is None


# US-10 AC1, AC2: ready / practised / mastered by type, practice bank only.
def test_question_bank_by_type(client: TestClient, db_session: Session, practice: Practice) -> None:
    # Red when: review-pipeline questions count, 'thuộc' ignores the last verdict, or a question
    # without a studied section with a card is ready.
    alice, subject = practice.user, practice.subject
    headers = headers_of(db_session, alice)
    kind = make_type(db_session, alice, subject, name="Giải thích")
    doc = make_document(db_session, alice, subject)
    studied = make_section(db_session, alice, doc, weight=2, studied_weight=2)
    unit = make_unit(db_session, alice, subject, status="canonical")
    db_session.add(
        UnitSection(user_id=alice.id, subject_id=subject.id, unit_id=unit.id, section_id=studied.id)
    )
    mastered, failed, fresh = (practice.question() for _ in range(3))
    review_only = practice.question()  # stays source review_auto: not in the bank
    for q in (mastered, failed, fresh):
        q.source, q.type_id = "bank", kind.id
    for q in (mastered, fresh):
        db_session.add(
            QuestionSection(
                user_id=alice.id, subject_id=subject.id, question_id=q.id, section_id=studied.id
            )
        )
    db_session.flush()
    practice.do(mastered, "correct", NOW - timedelta(hours=1))
    practice.do(failed, "incorrect", NOW - timedelta(hours=1))
    practice.do(review_only, "correct", NOW - timedelta(hours=1))
    bank = {t["question_type"]: t for t in one(stats(client, headers), subject)["bank"]}
    assert bank == {
        "Giải thích": {"question_type": "Giải thích", "ready": 2, "practiced": 2, "mastered": 1}
    }


# US-10 AC4, AC5, AC6, AC7: grid from creation to the exam; work = cards saved + answers.
def test_grid_counts_cards_and_answers_future_empty_exam_marked(
    client: TestClient, db_session: Session, practice: Practice
) -> None:
    # Red when: sitting time counts, a future event shows, the exam day is unmarked, or a streak
    # field appears.
    alice, subject = practice.user, practice.subject
    headers = headers_of(db_session, alice)
    subject.created_at = datetime(2026, 10, 18, 5, 0, tzinfo=UTC)
    doc = make_document(db_session, alice, subject)
    section = make_section(db_session, alice, doc, title="Mạng lớp 3")
    day19 = datetime(2026, 10, 19, 5, 0, tzinfo=UTC)
    save_card(db_session, alice, subject, day19, section.id)
    save_card(db_session, alice, subject, day19, section.id)
    question = practice.question()
    db_session.add(
        QuestionSection(
            user_id=alice.id, subject_id=subject.id, question_id=question.id, section_id=section.id
        )
    )
    answer(db_session, alice, question.id, day19 + timedelta(hours=1))
    answer(db_session, alice, question.id, NOW - timedelta(hours=1))
    answer(db_session, alice, question.id, NOW + timedelta(days=5))  # clock skew: still empty
    body = stats(client, headers)
    cells = {c["day"]: c for c in body["grid"]}
    assert min(cells) == "2026-10-18"
    assert cells["2026-10-19"]["cards_saved"] == 2
    assert cells["2026-10-19"]["questions_answered"] == 1
    assert cells["2026-10-19"]["subjects"] == [{"id": str(subject.id), "name": subject.name}]
    assert cells["2026-10-19"]["sections"] == [{"id": str(section.id), "name": "Mạng lớp 3"}]
    assert cells["2026-10-20"]["questions_answered"] == 1
    assert cells["2026-10-18"]["level"] == 0
    future = cells["2026-10-25"]
    assert future["future"] and future["level"] == 0 and future["questions_answered"] == 0
    exam = one(body, subject)["exam_date"]
    assert cells[exam]["exam_day"] and max(cells) == exam
    assert not any("streak" in key for key in body["grid"][0]) and "streak" not in body


# US-10 AC4: one subject or all; another user's subject id is a 404.
def test_filter_by_subject_and_unknown_subject_404(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: the filter leaks other subjects or accepts another user's subject id.
    alice, bob = two_users
    headers = headers_of(db_session, alice)
    mine, other = make_subject(db_session, alice, "A"), make_subject(db_session, alice, "B")
    theirs = make_subject(db_session, bob, "Của Bob")
    only = stats(client, headers, subject_id=str(mine.id))
    assert [s["id"] for s in only["subjects"]] == [str(mine.id)]
    assert {s["id"] for s in stats(client, headers)["subjects"]} == {str(mine.id), str(other.id)}
    for foreign in (theirs.id, uuid.uuid4()):
        response = client.get("/v1/stats", headers=headers, params={"subject_id": str(foreign)})
        assert response.status_code == 404


# US-10 AC8: Bob's data is in neither Alice's stats nor her CSV, whatever Bob did.
def test_stats_and_csv_are_isolated(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: any read drops the user_id filter.
    alice, bob = two_users
    a_headers = headers_of(db_session, alice)
    subject = make_subject(db_session, bob, "Bí mật của Bob")
    doc = make_document(db_session, bob, subject)
    section = make_section(db_session, bob, doc, title="Mục của Bob", weight=1, studied_weight=1)
    save_card(db_session, bob, subject, NOW - timedelta(days=1), section.id)
    question = make_question(db_session, bob, subject, n=7, source="bank")
    answer(db_session, bob, question.id, NOW - timedelta(hours=2))
    body = stats(client, a_headers)
    assert body["subjects"] == [] and body["grid"] == []
    text = client.get("/v1/export.csv", headers=a_headers).text
    assert "Bob" not in text
    assert list(csv.reader(io.StringIO(text)))[1:] == [["summary", "", "", "weeks_studied", "0"]]


# US-10 AC8, AC9: hours per week kept; a sitting left open counts to the last submitted answer.
def test_csv_hours_abandoned_sitting_counts_to_last_answer(
    client: TestClient, db_session: Session, practice: Practice
) -> None:
    # Red when: an open sitting counts zero, or counts to now instead of its last answer.
    alice = practice.user
    headers = headers_of(db_session, alice)
    question = practice.question()
    start = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)  # a Monday
    sessions = ReviewSessionRepository(db_session, alice.id)
    closed = sessions.start(start.date(), start)
    sessions.end(closed.id, start + timedelta(hours=1), reason="completed")
    opened = start + timedelta(days=1)
    answer(
        db_session,
        alice,
        question.id,
        opened + timedelta(minutes=30),
        started=opened,
        end=False,
    )
    response = client.get("/v1/export.csv", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["section", "subject", "period", "key", "value"]
    assert [r for r in rows if r[0] == "week"] == [["week", "", "2026-10-19", "hours", "1.50"]]
    assert ["summary", "", "", "weeks_studied", "1"] in rows


# US-10 AC8, US-12 AC2: an unverified account is refused on both routes.
def test_unverified_user_is_rejected(
    client: TestClient, db_session: Session, unverified_user: User
) -> None:
    token, _ = AuthSessionRepository(db_session).create(unverified_user.id, datetime.now(UTC))
    db_session.flush()
    headers = {"Authorization": f"Bearer {token}"}
    for path in ("/v1/stats", "/v1/export.csv"):
        response = client.get(path, headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"] == "email_not_verified"
    assert client.get("/v1/stats").status_code == 401
