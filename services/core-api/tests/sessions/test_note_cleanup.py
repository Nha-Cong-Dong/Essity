"""The `note_cleanup` job (T4.13b): notes whose URL was signed long ago and whose session never
confirmed them are deleted, file first and then row. Without it a URL could park files for free
and the rows would count against the account's note quota for ever."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from session_helpers import subject_of
from sqlalchemy import select
from sqlalchemy.orm import Session

import core_api.jobs.registry  # noqa: F401  # pyright: ignore[reportUnusedImport]  # registers kinds
from core_api.config import get_settings
from core_api.db.models import NoteUpload, StudySession, User
from core_api.domain.study_session import note_key
from core_api.jobs.app import app
from core_api.jobs.note_cleanup import NOTE_CLEANUP, delete_abandoned_notes
from fake_storage import FakeStorage

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
AGE = timedelta(hours=24)


def pending(db: Session, user: User, session: StudySession, n: int, at: datetime) -> NoteUpload:
    sha = f"{n:064x}"
    row = NoteUpload(
        session_id=session.id,
        object_key=note_key(user.id, session.id, sha, "image/jpeg"),
        sha256=sha,
        mime="image/jpeg",
        size_bytes=10,
        presigned_at=at,
    )
    row.user_id = user.id
    db.add(row)
    db.flush()
    return row


def draft(db: Session, user: User) -> StudySession:
    made = StudySession(
        subject_id=subject_of(db, user).id, description_raw="x", extraction="failed"
    )
    made.user_id = user.id
    db.add(made)
    db.flush()
    return made


def exists(db: Session, row: NoteUpload) -> bool:
    return db.scalar(select(NoteUpload.id).where(NoteUpload.id == row.id)) is not None


def test_old_pending_notes_go_file_and_row(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    # Red when: a recent note is deleted, or the file is left behind.
    alice, bob = two_users
    old = NOW - AGE - timedelta(seconds=1)
    recent = NOW - AGE + timedelta(seconds=1)
    a, b = draft(db_session, alice), draft(db_session, bob)
    gone = [pending(db_session, alice, a, 1, old), pending(db_session, bob, b, 2, old)]
    kept = pending(db_session, alice, a, 3, recent)
    storage = FakeStorage()
    for each in [*gone, kept]:
        storage.put(each.object_key, b"x", None)

    assert delete_abandoned_notes(db_session, storage, NOW, AGE) >= 2

    assert [exists(db_session, each) for each in gone] == [False, False]
    assert exists(db_session, kept)
    assert {each.object_key for each in gone} <= set(storage.deleted)
    assert kept.object_key not in storage.deleted


def test_a_file_never_uploaded_is_not_an_error(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    row = pending(db_session, alice, draft(db_session, alice), 1, NOW - AGE * 2)
    assert delete_abandoned_notes(db_session, FakeStorage(), NOW, AGE) >= 1
    assert not exists(db_session, row)


def test_store_down_keeps_the_rows_for_the_next_run(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    row = pending(db_session, alice, draft(db_session, alice), 1, NOW - AGE * 2)
    with pytest.raises(Exception, match="unreachable"):
        delete_abandoned_notes(db_session, FakeStorage(down=True), NOW, AGE)
    assert exists(db_session, row)


def test_cleanup_waits_twice_the_url_life_by_default() -> None:
    settings = get_settings()
    assert settings.note_cleanup_after_seconds >= 2 * settings.s3_presign_seconds


def test_note_cleanup_is_registered_as_hourly_periodic() -> None:
    assert hasattr(core_api.jobs.registry, "note_cleanup")
    registry: Any = app.periodic_registry
    assert registry.periodic_tasks[(NOTE_CLEANUP, NOTE_CLEANUP)].cron == "45 * * * *"
