"""The `document_cleanup` job (T4.5, plan R1, R2): uploads never confirmed, or refused, are
deleted, file and row, once their URL is long dead. Without it a URL could be used to park
files for free, and the rows would count against their owner's quota for ever.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

import core_api.jobs.registry  # noqa: F401  # pyright: ignore[reportUnusedImport]  # registers kinds
from clock import future_exam
from core_api.config import get_settings
from core_api.db.models import Document, User
from core_api.jobs.app import app
from core_api.jobs.document_cleanup import DOCUMENT_CLEANUP, delete_abandoned_uploads
from core_api.repositories.document import DocumentRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.user import UserRepository
from fake_storage import FakeStorage

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
AGE = timedelta(hours=1)


def document(session: Session, user: User, status: str, presigned_at: datetime, n: int) -> Document:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
    session.flush()
    made, _ = DocumentRepository(session, user.id).reserve(
        subject.id,
        sha256=f"{n:064x}",
        size_bytes=10,
        short_name="Tài liệu",
        now=presigned_at,
        quota_bytes=10**12,
        global_quota_bytes=10**15,
    )
    made.status = status
    made.uploaded_at = presigned_at if status == "uploaded" else None
    session.flush()
    return made


def exists(session: Session, document_id: uuid.UUID) -> bool:
    return session.scalar(select(Document.id).where(Document.id == document_id)) is not None


def test_old_unconfirmed_and_refused_uploads_go_file_and_row(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: an uploaded document is deleted, a recent upload is, or the file is left behind.
    alice, bob = two_users
    old = NOW - AGE - timedelta(seconds=1)
    recent = NOW - AGE + timedelta(seconds=1)
    gone = [
        document(db_session, alice, "pending", old, 1),
        document(db_session, bob, "rejected", old, 2),
    ]
    kept = [
        document(db_session, alice, "pending", recent, 3),
        document(db_session, alice, "uploaded", old - timedelta(days=30), 4),
    ]
    storage = FakeStorage()
    for each in gone + kept:
        storage.put(each.object_key, b"%PDF-", None)

    assert delete_abandoned_uploads(db_session, storage, NOW, AGE) >= 2

    assert [exists(db_session, each.id) for each in gone] == [False, False]
    assert [exists(db_session, each.id) for each in kept] == [True, True]
    assert {each.object_key for each in gone} <= set(storage.deleted)
    assert not {each.object_key for each in kept} & set(storage.deleted)


def test_a_file_already_gone_is_not_an_error(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # A refused file was deleted at confirm; a URL never used stored nothing.
    alice, _ = two_users
    old = document(db_session, alice, "rejected", NOW - AGE * 2, 1)
    assert delete_abandoned_uploads(db_session, FakeStorage(), NOW, AGE) >= 1
    assert not exists(db_session, old.id)


def test_store_down_keeps_the_rows_for_the_next_run(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # A row deleted with its file still stored would leave a file nothing accounts for.
    alice, _ = two_users
    old = document(db_session, alice, "pending", NOW - AGE * 2, 1)
    storage = FakeStorage(down=True)
    with pytest.raises(Exception, match="unreachable"):
        delete_abandoned_uploads(db_session, storage, NOW, AGE)
    assert exists(db_session, old.id)


def test_cleanup_waits_twice_the_url_life_by_default() -> None:
    settings = get_settings()
    assert settings.document_cleanup_after_seconds >= 2 * settings.s3_presign_seconds


def test_document_cleanup_is_registered_as_hourly_periodic() -> None:
    assert hasattr(core_api.jobs.registry, "document_cleanup")
    registry: Any = app.periodic_registry
    assert registry.periodic_tasks[(DOCUMENT_CLEANUP, DOCUMENT_CLEANUP)].cron == "15 * * * *"


# --- Two connections (plan R2): a row being confirmed is skipped, not deleted under it -------


@pytest.fixture
def committed_old_upload(engine: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t45-cleanup-{uuid.uuid4()}@example.com")
        session.flush()
        made = document(session, user, "pending", NOW - AGE * 2, 1)
        ids = (user.id, made.id)
        session.commit()
    yield ids
    with engine.begin() as connection:
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": ids[0]})


def test_a_document_being_confirmed_is_skipped(
    engine: Engine, committed_old_upload: tuple[uuid.UUID, uuid.UUID]
) -> None:
    # Red when: cleanup reads without SKIP LOCKED (it would wait, or delete a file that
    # confirm is announcing) or without a lock at all.
    user_id, document_id = committed_old_upload
    storage = FakeStorage()
    with Session(engine) as confirming, Session(engine) as cleaning:
        assert DocumentRepository(confirming, user_id).lock(document_id) is not None
        cleaning.execute(text("SET LOCAL lock_timeout = '2s'"))
        delete_abandoned_uploads(cleaning, storage, NOW, AGE)
        cleaning.commit()
        confirming.rollback()
    with Session(engine) as session:
        assert exists(session, document_id)
    assert not any(key.startswith(f"users/{user_id}/") for key in storage.deleted)


def test_a_document_signed_anew_is_kept(
    engine: Engine, committed_old_upload: tuple[uuid.UUID, uuid.UUID]
) -> None:
    # A new URL moves presigned_at: the row lives until that URL is long dead too (plan R2 b).
    _, document_id = committed_old_upload
    with Session(engine) as session:
        row = session.get_one(Document, document_id)
        row.presigned_at = NOW - AGE + timedelta(minutes=1)
        session.commit()
    with Session(engine) as cleaning:
        delete_abandoned_uploads(cleaning, FakeStorage(), NOW, AGE)
        cleaning.commit()
    with Session(engine) as session:
        assert exists(session, document_id)
