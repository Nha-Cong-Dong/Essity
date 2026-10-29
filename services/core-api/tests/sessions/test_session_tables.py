"""The study-session tables (T4.12, US-02 AC7, AC13): a session, its page ranges, its note files.

The database itself refuses another user's subject or document, a range the wrong way round,
a confirmed session without its dates, and the same note twice.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models import Document, Subject, User
from core_api.db.models.study_session import NoteFile, SessionRange, StudySession
from core_api.domain.documents import raw_key
from documents.test_document_table import SHA, subject_of

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)


def draft(user: User, subject: Subject, **overrides: object) -> StudySession:
    values: dict[str, object] = {
        "subject_id": subject.id,
        "description_raw": "học chương 3",
        "status": "draft",
        "extraction": "failed",
    }
    values.update(overrides)
    return StudySession(user_id=user.id, **values)


def document_of(session: Session, user: User, subject: Subject) -> Document:
    document = Document(
        user_id=user.id,
        subject_id=subject.id,
        short_name="Chương 3",
        sha256=SHA,
        size_bytes=10,
        status="uploaded",
        presigned_at=NOW,
        uploaded_at=NOW,
        object_key=raw_key(user.id, subject.id, SHA),
    )
    session.add(document)
    session.flush()
    return document


def rejected(db_session: Session, row: object) -> None:
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(row)
        db_session.flush()


def test_session_on_another_users_subject_is_refused(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    subject = subject_of(db_session, alice)
    rejected(db_session, draft(bob, subject))


def test_a_draft_may_not_carry_confirmation(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    rejected(db_session, draft(alice, subject, confirmed_at=NOW))


def test_confirmed_needs_dates_and_studied_not_after_logged(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    rejected(db_session, draft(alice, subject, status="confirmed"))
    rejected(
        db_session,
        draft(
            alice,
            subject,
            status="confirmed",
            confirmed_at=NOW,
            studied_on=date(2026, 10, 30),
            learning_day=date(2026, 10, 29),
        ),
    )


def test_description_must_not_be_blank(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    rejected(db_session, draft(alice, subject, description_raw="   "))


def test_range_rules_and_foreign_keys(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    subject = subject_of(db_session, alice)
    document = document_of(db_session, alice, subject)
    study = draft(alice, subject)
    db_session.add(study)
    db_session.flush()

    def rng(user: User, **o: object) -> SessionRange:
        values: dict[str, object] = {
            "session_id": study.id,
            "document_id": document.id,
            "start_page": 1,
            "end_page": 3,
            "depth": "deep",
            "position": 0,
        }
        values.update(o)
        return SessionRange(user_id=user.id, **values)

    rejected(db_session, rng(alice, start_page=5, end_page=2))
    rejected(db_session, rng(alice, start_page=0))
    rejected(db_session, rng(alice, depth="wild"))
    rejected(db_session, rng(bob))
    db_session.add(rng(alice))
    db_session.flush()
    rejected(db_session, rng(alice))  # same position


def test_note_key_must_be_the_servers_and_unique_per_session(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    subject = subject_of(db_session, alice)
    study = draft(alice, subject)
    db_session.add(study)
    db_session.flush()
    key = f"users/{alice.id}/sessions/{study.id}/notes/{SHA}.png"

    def note(user: User, **o: object) -> NoteFile:
        values: dict[str, object] = {
            "session_id": study.id,
            "object_key": key,
            "sha256": SHA,
            "mime": "image/png",
            "size_bytes": 5,
        }
        values.update(o)
        return NoteFile(user_id=user.id, **values)

    rejected(db_session, note(alice, object_key=f"users/{bob.id}/sessions/{study.id}/notes/x.png"))
    rejected(db_session, note(alice, mime="image/gif"))
    rejected(db_session, note(bob))
    db_session.add(note(alice))
    db_session.flush()
    rejected(db_session, note(alice))  # AC13: the same file twice


def test_deleting_the_subject_removes_the_session(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    study = draft(alice, subject)
    db_session.add(study)
    db_session.flush()
    db_session.execute(text("DELETE FROM subject WHERE id = :i"), {"i": subject.id})
    left = db_session.execute(
        text("SELECT count(*) FROM study_session WHERE subject_id = :i"), {"i": subject.id}
    ).scalar_one()
    assert left == 0
