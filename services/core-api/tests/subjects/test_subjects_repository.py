"""T1.19: a subject with its one exam (Q17; plan B17, B18)."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clock import FROZEN_NOW, future_exam
from core_api.db.models import User
from core_api.repositories.subject import ExamRepository, SubjectRepository

EXAM_DAY = future_exam(60)


def test_create_with_exam_writes_both(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, _ = two_users
    subject, exam = SubjectRepository(db_session, alice.id).create_with_exam(
        "Mạng máy tính", EXAM_DAY
    )
    assert (exam.subject_id, exam.exam_date, exam.user_id) == (subject.id, EXAM_DAY, alice.id)


def test_b17_a_subject_has_at_most_one_exam(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject, _ = SubjectRepository(db_session, alice.id).create_with_exam("Mạng máy tính", EXAM_DAY)
    db_session.flush()
    ExamRepository(db_session, alice.id).create(subject.id, future_exam(77))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_list_with_exams_is_ordered_by_exam_date_and_hides_deleted(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    subjects = SubjectRepository(db_session, alice.id)
    later, _ = subjects.create_with_exam("Hệ điều hành", future_exam(77))
    sooner, _ = subjects.create_with_exam("Mạng máy tính", future_exam(60))
    gone, _ = subjects.create_with_exam("Đã bỏ", future_exam(45))
    SubjectRepository(db_session, bob.id).create_with_exam("Của Bob", future_exam(46))
    db_session.flush()
    subjects.soft_delete(gone.id, FROZEN_NOW)
    db_session.flush()
    listed = subjects.list_with_exams()
    assert [(s.id, e.exam_date) for s, e, _ in listed] == [
        (sooner.id, future_exam(60)),
        (later.id, future_exam(77)),
    ]


def test_update_changes_name_and_exam_date(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    subject, _ = subjects.create_with_exam("Mạng", EXAM_DAY)
    db_session.flush()
    updated = subjects.update(subject.id, name="Mạng máy tính", exam_date=future_exam(105))
    assert updated is not None
    assert (updated[0].name, updated[1].exam_date) == ("Mạng máy tính", future_exam(105))


def test_update_leaves_out_what_is_not_given(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    subject, _ = subjects.create_with_exam("Mạng máy tính", EXAM_DAY)
    db_session.flush()
    updated = subjects.update(subject.id, name="Mạng")
    assert updated is not None and updated[1].exam_date == EXAM_DAY


def test_b18_bob_updating_alices_subject_finds_nothing_and_changes_nothing(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    subject, _ = SubjectRepository(db_session, alice.id).create_with_exam("Mạng máy tính", EXAM_DAY)
    db_session.flush()
    bobs = SubjectRepository(db_session, bob.id)
    assert bobs.update(subject.id, name="Của Bob", exam_date=date(2028, 1, 1)) is None
    assert bobs.get_with_exam(subject.id) is None
    db_session.flush()
    db_session.expire_all()
    mine = SubjectRepository(db_session, alice.id).get_with_exam(subject.id)
    assert mine is not None
    assert (mine[0].name, mine[1].exam_date) == ("Mạng máy tính", EXAM_DAY)


def test_update_of_a_deleted_subject_finds_nothing(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    subject, _ = subjects.create_with_exam("Mạng máy tính", EXAM_DAY)
    db_session.flush()
    subjects.soft_delete(subject.id, FROZEN_NOW)
    assert subjects.update(subject.id, name="Mạng") is None
