"""T2.9: a session's questions, fixed when it starts (`review_session_item`, plan C1, C3), and one
open session per learning day (plan C4). Database rules; the routes are tested in tests/today."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_t23_review_history import _assert_append_only_isolated  # pyright: ignore[reportPrivateUsage]

from core_api.db.models import Question, User
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import ReviewSessionItemRepository, ReviewSessionRepository
from core_api.repositories.subject import SubjectRepository

RUN = uuid.uuid4()
NOW = datetime(2026, 10, 25, 13, 0, tzinfo=UTC)
DAY = date(2026, 10, 25)


def questions(session: Session, user: User, n: int) -> list[Question]:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", date(2026, 12, 15))
    repo = QuestionRepository(session, user.id)
    return [
        repo.add_idempotent(subject.id, level=1, prompt=f"q{k}?", reference_answer="a", run_id=RUN)
        for k in range(n)
    ]


def refused(session: Session, sql: str, **params: object) -> None:
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(text(sql), params)


def test_t29_items_keep_their_order(db_session: Session, two_users: tuple[User, User]) -> None:
    alice = two_users[0]
    qs = questions(db_session, alice, 3)
    sitting = ReviewSessionRepository(db_session, alice.id).start(DAY, NOW)
    items = ReviewSessionItemRepository(db_session, alice.id)
    items.add_all(sitting.id, [q.id for q in reversed(qs)])
    assert [i.question_id for i in items.of_session(sitting.id)] == [q.id for q in reversed(qs)]
    assert [i.position for i in items.of_session(sitting.id)] == [1, 2, 3]


# Red when: a question can be listed twice in one session, or at position 0.
def test_t29_a_question_once_per_session_from_position_one(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    (q,) = questions(db_session, alice, 1)
    sitting = ReviewSessionRepository(db_session, alice.id).start(DAY, NOW)
    ReviewSessionItemRepository(db_session, alice.id).add_all(sitting.id, [q.id])
    insert = (
        "INSERT INTO review_session_item (id, user_id, review_session_id, position, question_id)"
        " VALUES (gen_random_uuid(), :u, :s, :p, :q)"
    )
    refused(db_session, insert, u=alice.id, s=sitting.id, p=2, q=q.id)
    refused(db_session, insert, u=alice.id, s=sitting.id, p=0, q=uuid.uuid4())


# ARCH §6.2. Red when: B's item can point at A's session or question.
def test_t29_items_cannot_point_at_another_users_rows(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    (q,) = questions(db_session, alice, 1)
    sitting = ReviewSessionRepository(db_session, alice.id).start(DAY, NOW)
    refused(
        db_session,
        "INSERT INTO review_session_item (id, user_id, review_session_id, position, question_id)"
        " VALUES (gen_random_uuid(), :u, :s, 1, :q)",
        u=bob.id,
        s=sitting.id,
        q=q.id,
    )


# Plan C3. Red when: a session's list can be changed after it starts.
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE review_session_item SET position = 9",
        "DELETE FROM review_session_item",
        "TRUNCATE review_session_item",
    ],
)
def test_t29_items_are_append_only(
    db_session: Session, two_users: tuple[User, User], sql: str
) -> None:
    alice = two_users[0]
    (q,) = questions(db_session, alice, 1)
    sitting = ReviewSessionRepository(db_session, alice.id).start(DAY, NOW)
    ReviewSessionItemRepository(db_session, alice.id).add_all(sitting.id, [q.id])
    with pytest.raises(IntegrityError, match="is refused"), db_session.begin_nested():
        db_session.execute(text(sql))


def test_t29_items_isolated(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    (q,) = questions(db_session, alice, 1)
    sitting = ReviewSessionRepository(db_session, alice.id).start(DAY, NOW)

    (item,) = ReviewSessionItemRepository(db_session, alice.id).add_all(sitting.id, [q.id])
    _assert_append_only_isolated(db_session, ReviewSessionItemRepository, alice, bob, item)


# Plan C4. Red when: two tabs can each open a session for the same learning day.
def test_t29_one_open_session_per_learning_day(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    sessions = ReviewSessionRepository(db_session, alice.id)
    first, created = sessions.open_for_day(DAY, NOW)
    assert created
    again, created_again = sessions.open_for_day(DAY, NOW)
    assert (again.id, created_again) == (first.id, False)
    # Another user, another day, or after the first is closed: a new one.
    assert ReviewSessionRepository(db_session, bob.id).open_for_day(DAY, NOW)[1]
    assert sessions.open_for_day(date(2026, 10, 26), NOW)[1]
    sessions.end(first.id, NOW, reason="completed")
    assert sessions.open_for_day(DAY, NOW)[1]
