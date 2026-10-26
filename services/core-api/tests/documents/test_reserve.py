"""`DocumentRepository.reserve`: the row an upload URL is signed for (T4.5, plan R1, R2, P6, P8,
P16, P17).

One user's reservations go one at a time (their user row is held FOR NO KEY UPDATE), so two
requests cannot both fit under the quota. The same file again in a subject is the same row.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from clock import future_exam
from core_api.db.models import Document, Subject, User
from core_api.repositories.document import (
    DocumentRejectedError,
    DocumentRepository,
    QuotaExceededError,
    SizeMismatchError,
    StorageFullError,
)
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.user import UserRepository
from races import finished, in_thread, wait_for_lock

NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
MB = 1024 * 1024
QUOTA = 10 * MB
EVERYONE = 10**15  # global cap far away, unless a test is about it
LOCK_NOT_AVAILABLE = "55P03"


def sha(n: int) -> str:
    return f"{n:064x}"


def subject_of(session: Session, user: User) -> Subject:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
    session.flush()
    return subject


def reserve(
    session: Session,
    user_id: uuid.UUID,
    subject_id: uuid.UUID,
    n: int,
    size: int = MB,
    *,
    now: datetime = NOW,
    quota: int = QUOTA,
    everyone: int = EVERYONE,
) -> tuple[Document, bool]:
    return DocumentRepository(session, user_id).reserve(
        subject_id,
        sha256=sha(n),
        size_bytes=size,
        short_name=f"Tài liệu {n}",
        now=now,
        quota_bytes=quota,
        global_quota_bytes=everyone,
    )


def test_a_new_file_gets_a_pending_row_at_its_raw_key(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    document, created = reserve(db_session, alice.id, subject.id, 1)
    assert created
    assert (document.status, document.presigned_at, document.size_bytes) == ("pending", NOW, MB)
    assert document.object_key == f"users/{alice.id}/subjects/{subject.id}/raw/{sha(1)}.pdf"
    assert document.short_name == "Tài liệu 1"


def test_another_users_subject_is_not_found(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    alices = subject_of(db_session, alice)
    with pytest.raises(SubjectNotFoundError):
        reserve(db_session, bob.id, alices.id, 1)
    assert db_session.scalar(select(func.count()).select_from(Document)) == 0


def test_a_deleted_subject_is_not_found(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    SubjectRepository(db_session, alice.id).soft_delete(subject.id, NOW)
    with pytest.raises(SubjectNotFoundError):
        reserve(db_session, alice.id, subject.id, 1)


def test_an_uploaded_file_again_is_the_same_row_untouched(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    first, _ = reserve(db_session, alice.id, subject.id, 1)
    first.status, first.uploaded_at = "uploaded", NOW
    db_session.flush()

    again, created = reserve(db_session, alice.id, subject.id, 1, now=NOW + timedelta(hours=1))

    assert (again.id, created, again.presigned_at, again.status) == (
        first.id,
        False,
        NOW,
        "uploaded",
    )


def test_a_pending_file_again_is_the_same_row_signed_anew(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # presigned_at moves on, so cleanup waits for the new URL to die too (plan R2).
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    first, _ = reserve(db_session, alice.id, subject.id, 1)
    later = NOW + timedelta(minutes=30)

    again, created = reserve(db_session, alice.id, subject.id, 1, now=later)

    assert (again.id, created, again.presigned_at, again.short_name) == (
        first.id,
        False,
        later,
        "Tài liệu 1",
    )


def test_a_pending_file_again_with_another_size_is_refused(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    first, _ = reserve(db_session, alice.id, subject.id, 1, MB)
    with pytest.raises(SizeMismatchError):
        reserve(db_session, alice.id, subject.id, 1, 2 * MB, now=NOW + timedelta(minutes=1))
    assert (first.size_bytes, first.presigned_at) == (MB, NOW)


def test_a_rejected_file_again_is_refused(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # The same SHA-256 is the same bytes: it would be refused again (plan R1).
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    first, _ = reserve(db_session, alice.id, subject.id, 1)
    first.status = "rejected"
    db_session.flush()
    with pytest.raises(DocumentRejectedError):
        reserve(db_session, alice.id, subject.id, 1)


def test_the_quota_counts_every_row_of_the_account(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    statuses = ["pending", "uploaded", "rejected"]
    for n, status in enumerate(statuses):
        document, _ = reserve(db_session, alice.id, subject.id, n, 3 * MB)
        document.status = status
        document.uploaded_at = NOW if status == "uploaded" else None
    db_session.flush()

    reserve(db_session, alice.id, subject.id, 10, MB)  # 9 + 1 = 10 MB: exactly the quota
    with pytest.raises(QuotaExceededError):
        reserve(db_session, alice.id, subject.id, 11, 1)


def test_the_quota_is_per_account(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    reserve(db_session, alice.id, subject_of(db_session, alice).id, 1, QUOTA)
    reserve(db_session, bob.id, subject_of(db_session, bob).id, 1, QUOTA)


def test_signing_a_pending_file_again_does_not_count_it_twice(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    subject = subject_of(db_session, alice)
    reserve(db_session, alice.id, subject.id, 1, QUOTA)
    reserve(db_session, alice.id, subject.id, 1, QUOTA)  # at the quota, but already counted


def test_the_store_has_a_cap_for_everyone(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    reserve(db_session, alice.id, subject_of(db_session, alice).id, 1, 4 * MB)
    stored: int = db_session.scalar(select(func.coalesce(func.sum(Document.size_bytes), 0))) or 0
    bobs = subject_of(db_session, bob)
    with pytest.raises(StorageFullError):
        reserve(db_session, bob.id, bobs.id, 1, MB, everyone=stored + MB - 1)
    reserve(db_session, bob.id, bobs.id, 1, MB, everyone=stored + MB)


# --- Two connections (plan P16): the user row is the lock -------------------------------------


@pytest.fixture
def committed(engine: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t45-race-{uuid.uuid4()}@example.com")
        session.flush()
        subject = subject_of(session, user)
        ids = (user.id, subject.id)
        session.commit()
    yield ids
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": ids[0]})


def test_two_reservations_of_one_user_go_one_at_a_time(
    engine: Engine, committed: tuple[uuid.UUID, uuid.UUID]
) -> None:
    # Red when: reserve sums the quota without holding the user row: both would fit.
    user_id, subject_id = committed
    with Session(engine) as first, Session(engine) as second:
        reserve(first, user_id, subject_id, 1, 6 * MB)
        second.execute(text("SET LOCAL lock_timeout = '15s'"))
        pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(lambda: reserve(second, user_id, subject_id, 2, 6 * MB))
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        second.rollback()
    assert isinstance(result, QuotaExceededError), result


def test_the_owner_lock_lets_sign_ins_through(
    engine: Engine, committed: tuple[uuid.UUID, uuid.UUID]
) -> None:
    # FOR NO KEY UPDATE, not FOR UPDATE: a row with a foreign key to the user (a new login
    # session) takes KEY SHARE and must not wait for an upload (plan P8).
    user_id, subject_id = committed
    with Session(engine) as uploading, Session(engine) as signing_in:
        reserve(uploading, user_id, subject_id, 1)
        signing_in.execute(text("SET LOCAL lock_timeout = '200ms'"))
        signing_in.execute(
            text('SELECT id FROM "user" WHERE id = :id FOR KEY SHARE'), {"id": user_id}
        )
        signing_in.rollback()
        uploading.rollback()


def test_a_reservation_waits_while_the_subject_is_being_deleted(
    engine: Engine, committed: tuple[uuid.UUID, uuid.UUID]
) -> None:
    user_id, subject_id = committed
    with Session(engine) as deleter, Session(engine) as uploading:
        SubjectRepository(deleter, user_id).soft_delete(subject_id, NOW)
        uploading.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(OperationalError) as refused:
            reserve(uploading, user_id, subject_id, 1)
        assert getattr(refused.value.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE
        uploading.rollback()
        deleter.rollback()
