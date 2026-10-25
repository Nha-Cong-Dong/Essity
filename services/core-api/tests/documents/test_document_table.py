"""The `document` table (T4.5, ADR-0012): one row per file of a subject, owned by one user.

The database itself refuses a row pointing at another user's subject or file, two rows for the
same file in a subject, and states that do not add up.
"""

import uuid
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clock import future_exam
from core_api.db.models import Document, Subject, User
from core_api.domain.documents import raw_key
from core_api.repositories.document import DocumentRepository
from core_api.repositories.subject import SubjectRepository
from isolation import assert_isolated

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
SHA = "ab" * 32


def subject_of(session: Session, user: User) -> Subject:
    subject, _ = SubjectRepository(session, user.id).create_with_exam(
        "Mạng máy tính", future_exam(60)
    )
    session.flush()
    return subject


def pending(user: User, subject: Subject, sha256: str = SHA, **overrides: object) -> Document:
    values: dict[str, object] = {
        "subject_id": subject.id,
        "short_name": "Chương 3",
        "sha256": sha256,
        "size_bytes": 1234,
        "status": "pending",
        "presigned_at": NOW,
    }
    values.update(overrides)
    if "object_key" not in values:
        values["object_key"] = raw_key(user.id, subject.id, sha256)
    return Document(**values)


def test_documents_are_isolated(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    subject = subject_of(db_session, alice)
    assert_isolated(
        db_session,
        DocumentRepository,
        alice,
        bob,
        lambda repository: repository.add(pending(alice, subject)),
    )


def test_a_document_cannot_hang_on_another_users_subject(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    alices = subject_of(db_session, alice)
    # Even with a key in Bob's own space: the composite foreign key refuses the subject.
    DocumentRepository(db_session, bob.id).add(
        pending(bob, alices, object_key=raw_key(bob.id, alices.id, SHA))
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    "wrong",
    ["other user", "other subject", "other file", "other type", "derived"],
)
def test_the_object_key_is_always_the_rows_own_raw_key(
    db_session: Session, two_users: tuple[User, User], wrong: str
) -> None:
    alice, bob = two_users
    subject = subject_of(db_session, alice)
    own = raw_key(alice.id, subject.id, SHA)
    key = {
        "other user": raw_key(bob.id, subject.id, SHA),
        "other subject": raw_key(alice.id, uuid.uuid4(), SHA),
        "other file": raw_key(alice.id, subject.id, "cd" * 32),
        "other type": own.replace(".pdf", ".png"),
        "derived": own.replace("/raw/", "/derived/"),
    }[wrong]
    DocumentRepository(db_session, alice.id).add(pending(alice, subject, object_key=key))
    with pytest.raises(IntegrityError, match="object_key_is_raw_key"):
        db_session.flush()


def test_one_row_per_file_and_subject(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    documents = DocumentRepository(db_session, alice.id)
    documents.add(pending(alice, subject))
    db_session.flush()
    documents.add(pending(alice, subject))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_the_same_file_in_two_subjects_is_two_documents(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    first, second = subject_of(db_session, alice), subject_of(db_session, alice)
    documents = DocumentRepository(db_session, alice.id)
    documents.add(pending(alice, first))
    documents.add(pending(alice, second))
    db_session.flush()
    assert len(documents.list()) == 2


def test_two_users_may_hold_the_same_file(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Never deduplicated across users: that would tell Bob what Alice uploaded.
    alice, bob = two_users
    for user in (alice, bob):
        DocumentRepository(db_session, user.id).add(pending(user, subject_of(db_session, user)))
    db_session.flush()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"sha256": "AB" * 32}, "sha256_hex"),
        ({"sha256": "ab" * 31}, "sha256_hex"),
        ({"size_bytes": 0}, "size_positive"),
        ({"status": "indexed"}, "status_known"),
        ({"short_name": "   "}, "short_name_not_blank"),
        ({"status": "uploaded"}, "uploaded_at_iff_uploaded"),
        ({"uploaded_at": NOW}, "uploaded_at_iff_uploaded"),
        ({"page_count": 0}, "page_count_from_one"),
    ],
)
def test_states_that_do_not_add_up_are_refused(
    db_session: Session,
    two_users: tuple[User, User],
    overrides: dict[str, object],
    constraint: str,
) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    sha = str(overrides.get("sha256", SHA))
    if "sha256" in overrides:
        overrides = overrides | {
            "object_key": f"users/{alice.id}/subjects/{subject.id}/raw/{sha}.pdf"
        }
    DocumentRepository(db_session, alice.id).add(pending(alice, subject, **overrides))
    with pytest.raises(IntegrityError, match=constraint):
        db_session.flush()


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_unconfirmed_states_have_no_upload_time(
    db_session: Session, two_users: tuple[User, User], status: str
) -> None:
    alice, _ = two_users
    DocumentRepository(db_session, alice.id).add(
        pending(alice, subject_of(db_session, alice), status=status)
    )
    db_session.flush()


def test_an_uploaded_document_has_its_time(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    DocumentRepository(db_session, alice.id).add(
        pending(alice, subject_of(db_session, alice), status="uploaded", uploaded_at=NOW)
    )
    db_session.flush()


def test_0013_up_down_up(engine: Engine, alembic_cfg: Config) -> None:
    try:
        command.downgrade(alembic_cfg, "0012")
        assert "document" not in inspect(engine).get_table_names()
        command.upgrade(alembic_cfg, "0013")
        with engine.connect() as connection:
            index = connection.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_document_unconfirmed'")
            ).scalar_one()
        assert "(presigned_at)" in index
        assert "<> 'uploaded'" in index
    finally:
        command.upgrade(alembic_cfg, "head")
