from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models import Exam, Subject, User
from core_api.repositories.subject import ExamRepository, SubjectNotFoundError, SubjectRepository
from isolation import assert_isolated

EXAM_DAY = date(2027, 1, 15)


def test_subjects_are_isolated(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    assert_isolated(db_session, SubjectRepository, alice, bob, lambda r: r.create("Mạng máy tính"))


def test_exams_are_isolated(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users

    def create_exam(exams: ExamRepository) -> Exam:
        subject = SubjectRepository(db_session, exams.user_id).create("Mạng máy tính")
        db_session.flush()
        return exams.create(subject.id, EXAM_DAY)

    assert_isolated(db_session, ExamRepository, alice, bob, create_exam)


def test_exam_cannot_be_attached_to_another_users_subject(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    bobs_subject = SubjectRepository(db_session, bob.id).create("Hệ điều hành")
    db_session.flush()
    with pytest.raises(SubjectNotFoundError):
        ExamRepository(db_session, alice.id).create(bobs_subject.id, EXAM_DAY)


def test_database_refuses_an_exam_whose_owner_differs_from_its_subjects(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Even raw SQL cannot attach Alice's exam to Bob's subject: (subject_id, user_id) is a
    # composite foreign key to subject.
    alice, bob = two_users
    bobs_subject = SubjectRepository(db_session, bob.id).create("Hệ điều hành")
    db_session.flush()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO exam (id, user_id, subject_id, exam_date) "
                "VALUES (gen_random_uuid(), :user_id, :subject_id, :day)"
            ),
            {"user_id": alice.id, "subject_id": bobs_subject.id, "day": EXAM_DAY},
        )


def test_subject_name_is_trimmed_and_cannot_be_blank(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    subjects = SubjectRepository(db_session, two_users[0].id)
    assert subjects.create("  Mạng máy tính ").name == "Mạng máy tính"
    for blank in ("", "   "):
        with pytest.raises(ValueError):
            subjects.create(blank)


def test_soft_deleted_subject_is_hidden(db_session: Session, two_users: tuple[User, User]) -> None:
    subjects = SubjectRepository(db_session, two_users[0].id)
    subject = subjects.create("Mạng máy tính")
    db_session.flush()
    assert subjects.soft_delete(subject.id) is True
    db_session.flush()
    assert subjects.get(subject.id) is None
    assert subjects.list() == []
    assert subject.deleted_at is not None  # kept in the database, hidden from the app


def test_soft_delete_of_another_users_subject_does_nothing(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    subject = SubjectRepository(db_session, alice.id).create("Mạng máy tính")
    db_session.flush()
    assert SubjectRepository(db_session, bob.id).soft_delete(subject.id) is False
    assert subject.deleted_at is None


def test_exams_for_subject(db_session: Session, two_users: tuple[User, User]) -> None:
    alice = two_users[0]
    subject = SubjectRepository(db_session, alice.id).create("Mạng máy tính")
    db_session.flush()
    exams = ExamRepository(db_session, alice.id)
    exam = exams.create(subject.id, EXAM_DAY)
    db_session.flush()
    assert list(exams.for_subject(subject.id)) == [exam]


def test_deleting_a_user_deletes_their_subjects_and_exams(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    subject = SubjectRepository(db_session, alice.id).create("Mạng máy tính")
    db_session.flush()
    ExamRepository(db_session, alice.id).create(subject.id, EXAM_DAY)
    db_session.flush()
    db_session.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": alice.id})
    assert db_session.scalar(select(func.count()).select_from(Subject)) == 0
    assert db_session.scalar(select(func.count()).select_from(Exam)) == 0
