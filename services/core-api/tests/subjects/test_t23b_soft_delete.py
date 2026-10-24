"""T2.3b: soft-deleting a subject with no review history (us-01 AC8), repository and PATCH side.

Plan `docs/plans/t2.3b-subject-soft-delete.md` (F3, F6, F9, F10). A subject with any attempt,
a draft included (F2), keeps its place; deleting hides it and its exam, questions and units.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from clock import FROZEN_NOW, future_exam
from core_api.api.subjects import SubjectChange, change_subject
from core_api.db.models import User
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import AttemptRepository, ReviewSessionRepository
from core_api.repositories.subject import (
    SubjectHasHistoryError,
    SubjectNotFoundError,
    SubjectRepository,
)
from core_api.repositories.user import UserRepository
from races import finished, in_thread, wait_for_lock

RUN = uuid.uuid4()
DAY = date(2026, 10, 23)


def with_attempt(session: Session, user: User, subject_id: uuid.UUID, *, submitted: bool) -> None:
    question = QuestionRepository(session, user.id).add_idempotent(
        subject_id, level=1, prompt=f"Câu {uuid.uuid4()}?", reference_answer="a", run_id=RUN
    )
    review = ReviewSessionRepository(session, user.id).start(DAY, FROZEN_NOW)
    attempts = AttemptRepository(session, user.id)
    attempt = attempts.create_draft(review.id, question.id)
    if submitted:
        attempts.submit(attempt.id, FROZEN_NOW)
    session.flush()


def deleted_at(session: Session, subject_id: uuid.UUID) -> datetime | None:
    return session.execute(
        text("SELECT deleted_at FROM subject WHERE id = :id"), {"id": subject_id}
    ).scalar_one()


# --- soft_delete (us-01 AC8) ----------------------------------------------------------------------


def test_us01_ac8_soft_delete_hides_the_subject_at_the_given_instant(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: `soft_delete` reads its own clock instead of the request's (R23/R34).
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    subject, _ = subjects.create_with_exam("Mạng", future_exam())
    db_session.flush()
    subjects.soft_delete(subject.id, FROZEN_NOW)
    db_session.flush()
    assert deleted_at(db_session, subject.id) == FROZEN_NOW
    assert subjects.get_with_exam(subject.id) is None
    assert subjects.list_with_exams() == []


@pytest.mark.parametrize("submitted", [False, True], ids=["draft", "submitted"])
def test_us01_ac8_a_subject_with_an_attempt_is_not_deleted(
    db_session: Session, two_users: tuple[User, User], submitted: bool
) -> None:
    # Red when: the history check goes, or counts only submitted attempts (a draft is work too, F2).
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    subject, _ = subjects.create_with_exam("Mạng", future_exam())
    with_attempt(db_session, alice, subject.id, submitted=submitted)
    with pytest.raises(SubjectHasHistoryError):
        subjects.soft_delete(subject.id, FROZEN_NOW)
    db_session.flush()
    assert deleted_at(db_session, subject.id) is None


def test_us01_ac8_a_subject_with_questions_but_no_attempt_is_deleted(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    subject, _ = subjects.create_with_exam("Mạng", future_exam())
    QuestionRepository(db_session, alice.id).add_idempotent(
        subject.id, level=1, prompt="TCP?", reference_answer="a", run_id=RUN
    )
    ReviewSessionRepository(db_session, alice.id).start(DAY, FROZEN_NOW)
    db_session.flush()
    subjects.soft_delete(subject.id, FROZEN_NOW)
    db_session.flush()
    assert deleted_at(db_session, subject.id) == FROZEN_NOW


def test_us01_ac8_deleting_someone_elses_subject_finds_nothing_and_changes_nothing(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    subject, _ = SubjectRepository(db_session, alice.id).create_with_exam("Mạng", future_exam())
    db_session.flush()
    with pytest.raises(SubjectNotFoundError):
        SubjectRepository(db_session, bob.id).soft_delete(subject.id, FROZEN_NOW)
    db_session.flush()
    assert deleted_at(db_session, subject.id) is None


def test_us01_ac8_deleting_twice_finds_nothing_the_second_time(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    subject, _ = subjects.create_with_exam("Mạng", future_exam())
    db_session.flush()
    subjects.soft_delete(subject.id, FROZEN_NOW)
    db_session.flush()
    with pytest.raises(SubjectNotFoundError):
        subjects.soft_delete(subject.id, FROZEN_NOW + timedelta(hours=1))
    assert deleted_at(db_session, subject.id) == FROZEN_NOW


def test_us01_ac8_the_name_can_be_used_again(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    subject, _ = subjects.create_with_exam("Mạng", future_exam())
    db_session.flush()
    subjects.soft_delete(subject.id, FROZEN_NOW)
    again, _ = subjects.create_with_exam("Mạng", future_exam())
    db_session.flush()
    assert [s.id for s, _, _ in subjects.list_with_exams()] == [again.id]


# --- has_history in the list (us-01 AC8, F6)


def test_us01_ac8_list_reports_has_history_per_subject(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: the column is missing, or it is not correlated to its own subject.
    alice, bob = two_users
    subjects = SubjectRepository(db_session, alice.id)
    fresh, _ = subjects.create_with_exam("Mới", future_exam(30))
    drafted, _ = subjects.create_with_exam("Đang làm", future_exam(40))
    done, _ = subjects.create_with_exam("Đã ôn", future_exam(50))
    with_attempt(db_session, alice, drafted.id, submitted=False)
    with_attempt(db_session, alice, done.id, submitted=True)
    bobs, _ = SubjectRepository(db_session, bob.id).create_with_exam("Của Bob", future_exam(35))
    with_attempt(db_session, bob, bobs.id, submitted=True)
    listed = {s.id: history for s, _, history in subjects.list_with_exams()}
    assert listed == {fresh.id: False, drafted.id: True, done.id: True}


# --- Two connections (F10: a PATCH that waited on a delete answers 404) ---------------------------


@dataclass
class Committed:
    user_id: uuid.UUID
    subject_id: uuid.UUID


@pytest.fixture
def committed_subject(engine: Engine) -> Iterator[Committed]:
    """A subject both connections can see: committed, removed afterwards (no review history, so
    no append-only trigger stands in the way)."""
    with Session(engine) as session:
        user = UserRepository(session).create(f"t23b-{uuid.uuid4()}@example.com")
        session.flush()
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam())
        made = Committed(user.id, subject.id)
        session.commit()
    yield made
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": made.user_id})


def test_us01_ac8_a_patch_waiting_on_a_delete_answers_404(
    engine: Engine, committed_subject: Committed
) -> None:
    # Red when: PATCH reads the subject without locking it (the ORM UPDATE then waits on the
    # delete and renames the deleted subject: name "Đổi tên").
    made = committed_subject
    with Session(engine) as deleter, Session(engine) as patcher:
        SubjectRepository(deleter, made.user_id).soft_delete(made.subject_id, FROZEN_NOW)
        patcher.execute(text("SET LOCAL lock_timeout = '15s'"))
        pid = patcher.execute(text("SELECT pg_backend_pid()")).scalar_one()
        user = patcher.get(User, made.user_id)
        assert user is not None
        thread, outcome = in_thread(
            lambda: change_subject(
                made.subject_id, SubjectChange(name="Đổi tên"), user, patcher, FROZEN_NOW
            )
        )
        wait_for_lock(engine, pid, outcome)
        deleter.commit()
        result = finished(thread, outcome)
        patcher.rollback()
    assert isinstance(result, HTTPException), result
    assert (result.status_code, result.detail) == (404, "subject_not_found")
    with Session(engine) as reader:
        name = reader.execute(
            text("SELECT name FROM subject WHERE id = :id"), {"id": made.subject_id}
        ).scalar_one()
    assert name == "Mạng"


def test_us01_ac8_a_patch_after_the_delete_answers_404(
    engine: Engine, committed_subject: Committed
) -> None:
    made = committed_subject
    with Session(engine) as deleter:
        SubjectRepository(deleter, made.user_id).soft_delete(made.subject_id, FROZEN_NOW)
        deleter.commit()
    with Session(engine) as patcher:
        user = patcher.get(User, made.user_id)
        assert user is not None
        with pytest.raises(HTTPException) as refused:
            change_subject(made.subject_id, SubjectChange(name="Đổi"), user, patcher, FROZEN_NOW)
    assert refused.value.status_code == 404
