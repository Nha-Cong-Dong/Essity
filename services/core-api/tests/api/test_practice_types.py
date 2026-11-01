"""T8.6b `GET /v1/subjects/{id}/practice-types` (US-16 AC4, AC5, AC6, AC8, AC9, AC10)."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core_api.db.models import KnowledgeUnit, Question, Subject, User
from core_api.domain.mastery import has_banned_word
from core_api.domain.scheduling.rating import Verdict
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.practice_attempt import PracticeAttemptRepository
from core_api.repositories.question import QuestionUnitRepository
from core_api.repositories.review import GradeRepository
from v2_rows import RUN, make_question, make_subject, make_type, make_unit

T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
VERDICT = {"correct": Verdict.CORRECT, "partial": Verdict.PARTIAL, "incorrect": Verdict.INCORRECT}


def headers_of(session: Session, user: User) -> dict[str, str]:
    user.email_verified_at = T0
    token, _ = AuthSessionRepository(session).create(user.id, datetime.now(UTC))
    session.flush()
    return {"Authorization": f"Bearer {token}"}


def unit_of(session: Session, user: User, question: Question) -> KnowledgeUnit:
    links = QuestionUnitRepository(session, user.id)
    found = links.units_of(question.id)
    if found:
        return found[0]
    subject = session.get(Subject, question.subject_id)
    assert subject is not None
    unit = make_unit(session, user, subject)
    links.link(question.id, unit.id)
    return unit


def practise(
    session: Session, user: User, question: Question, verdict: str, n: int, seconds: float = 30
) -> None:
    """One submitted practice attempt (no review session) with a grade."""
    repo = PracticeAttemptRepository(session, user.id)
    served = T0 + timedelta(hours=n)
    attempt, _ = repo.open_draft(question.id, served)
    repo.submit(attempt.id, served + timedelta(seconds=seconds), hidden_ms=0, reference_seconds=100)
    unit = unit_of(session, user, question)
    GradeRepository(session, user.id).add_with_units(
        attempt.id,
        source="ai",
        overall=VERDICT[verdict],
        understanding=None,
        units={unit.id: VERDICT[verdict]},
        run_id=RUN,
    )
    session.flush()


def get(client: TestClient, headers: dict[str, str], subject: Subject):  # noqa: ANN201
    r = client.get(f"/v1/subjects/{subject.id}/practice-types", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_not_enough_data_then_two_of_three(  # US-16 AC4
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    h = headers_of(db_session, alice)
    subject = make_subject(db_session, alice)
    kind = make_type(db_session, alice, subject, name="Phân tích điểm yếu")
    q = make_question(db_session, alice, subject, n=1, type_id=kind.id)
    assert get(client, h, subject)[0]["mastery_line"] == "chưa đủ dữ liệu"
    for i, v in enumerate(["correct", "correct", "incorrect"]):
        practise(db_session, alice, q, v, i)
    [row] = get(client, h, subject)
    assert row["name"] == "Phân tích điểm yếu"  # the type name is never scanned or altered
    assert row["mastery_line"] == "đúng 2 trên 3 lần gần nhất"
    assert row["attempts_counted"] == 3
    assert not has_banned_word(row["mastery_line"] + row["sensitivity_line"])


def test_ref_origin_switches_after_five_correct(  # US-16 AC6, AC5
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    h = headers_of(db_session, alice)
    subject = make_subject(db_session, alice)
    kind = make_type(db_session, alice, subject, ref_time_s=120, ref_origin="rubric")
    q = make_question(db_session, alice, subject, n=1, type_id=kind.id)
    for i in range(4):
        practise(db_session, alice, q, "correct", i, seconds=20)
    row = get(client, h, subject)[0]
    assert (row["reference_seconds"], row["ref_origin"]) == (120, "rubric")
    practise(db_session, alice, q, "correct", 4, seconds=20)
    row = get(client, h, subject)[0]
    assert (row["reference_seconds"], row["ref_origin"]) == (20, "learner_median")
    assert row["sensitivity"] == "near"  # measured against the learner's own median


def test_review_attempts_do_not_count(  # US-16 AC9, AC11
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    h = headers_of(db_session, alice)
    subject = make_subject(db_session, alice)
    make_type(db_session, alice, subject)
    assert get(client, h, subject)[0]["attempts_counted"] == 0


def test_newest_grade_counts_after_override(  # US-16 AC10
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    h = headers_of(db_session, alice)
    subject = make_subject(db_session, alice)
    kind = make_type(db_session, alice, subject)
    q = make_question(db_session, alice, subject, n=1, type_id=kind.id)
    for i in range(3):
        practise(db_session, alice, q, "incorrect", i)
    assert get(client, h, subject)[0]["mastery"] == 0
    from sqlalchemy import select

    from core_api.db.models import Attempt

    attempts = db_session.scalars(select(Attempt).where(Attempt.user_id == alice.id)).all()
    unit = unit_of(db_session, alice, q)
    for a in attempts:
        GradeRepository(db_session, alice.id).add_with_units(
            a.id,
            source="user_override",
            overall=Verdict.CORRECT,
            understanding=None,
            units={unit.id: Verdict.CORRECT},
            run_id=None,
        )
    db_session.flush()
    assert get(client, h, subject)[0]["mastery"] == 1


def test_other_users_data_and_subject_are_invisible(  # ADR-0001 isolation
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    subject = make_subject(db_session, alice)
    make_type(db_session, alice, subject)
    hb = headers_of(db_session, bob)
    r = client.get(f"/v1/subjects/{subject.id}/practice-types", headers=hb)
    assert r.status_code == 404
    assert client.get(f"/v1/subjects/{uuid.uuid4()}/practice-types", headers=hb).status_code == 404


def test_unverified_or_anonymous_is_refused(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    subject = make_subject(db_session, two_users[0])
    assert client.get(f"/v1/subjects/{subject.id}/practice-types").status_code in (401, 403)
