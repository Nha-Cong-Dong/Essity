"""Edges of T4.5 the other document tests leave open (feature-tester, mutation run on e984fdb).

Each test names the change to the code that turns it red. Data is committed here, through real
connections, and removed with its user afterwards.
"""

import hashlib
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from accounts import signed_in
from clock import future_exam
from core_api.api import documents as documents_api
from core_api.config import get_settings
from core_api.db.models import Document, Outbox
from core_api.jobs import document_cleanup
from core_api.main import app
from core_api.repositories.document import DocumentRepository
from core_api.repositories.subject import SubjectRepository
from core_api.security.client_ip import CLIENT_IP_HEADER
from core_api.security.service_token import SERVICE_TOKEN_HEADER
from fake_storage import FakeStorage
from races import finished, in_thread

PDF = b"%PDF-1.7\n" + b"x" * 100
PDF_SHA = hashlib.sha256(PDF).hexdigest()
PDF_SHA_B64 = "dcDLsbHDXF6qpwyQZaowiQP42JPB37gwUxpRS1GrToU="
WEB_TOKEN = "edge-web-token-0123456789abcdefghijkl"
LOCK_NOT_AVAILABLE = "55P03"
SECONDS_TO_WAIT = 5.0


@dataclass
class Account:
    user_id: uuid.UUID
    headers: dict[str, str]
    subject_id: uuid.UUID


@pytest.fixture
def account(engine: Engine) -> Iterator[Account]:
    with Session(engine) as session:
        user, headers = signed_in(session)
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
        made = Account(user.id, headers, subject.id)
        session.commit()
    yield made
    with engine.begin() as connection:
        # The outbox keeps no foreign key to the user: by hand.
        connection.execute(text("DELETE FROM outbox WHERE user_id = :u"), {"u": made.user_id})
        connection.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": made.user_id})


@pytest.fixture
def app_client(monkeypatch: pytest.MonkeyPatch, fake_storage: FakeStorage) -> TestClient:
    """The app with its own sessions: each request commits or rolls back for real."""
    monkeypatch.setenv("CORE_WEB_TOKEN", WEB_TOKEN)
    get_settings.cache_clear()
    headers = {SERVICE_TOKEN_HEADER: WEB_TOKEN, CLIENT_IP_HEADER: "10.45.9.1"}
    return TestClient(app, headers=headers, raise_server_exceptions=False)


def pending_document(session: Session, who: Account, presigned_at: datetime) -> Document:
    document, _ = DocumentRepository(session, who.user_id).reserve(
        who.subject_id,
        sha256=PDF_SHA,
        size_bytes=len(PDF),
        short_name="Chương 3",
        now=presigned_at,
        quota_bytes=10**12,
        global_quota_bytes=10**15,
    )
    return document


def wait_until_blocked_by(engine: Engine, blocker_pid: int, outcome: list[object]) -> None:
    """Until some backend waits on a lock `blocker_pid` holds; fail if the work finished first."""
    deadline = time.monotonic() + SECONDS_TO_WAIT
    with engine.connect() as watcher:
        while time.monotonic() < deadline:
            if outcome:
                pytest.fail(f"finished without waiting for the subject's lock: {outcome!r}")
            blocked = watcher.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE :p = ANY(pg_blocking_pids(pid))"),
                {"p": blocker_pid},
            ).scalar_one()
            if blocked:
                return
            watcher.rollback()
            time.sleep(0.05)
    pytest.fail("nothing ever waited for the subject's lock")


def test_signing_a_pending_file_anew_waits_while_its_subject_is_being_deleted(
    engine: Engine, account: Account
) -> None:
    # Red when: `hold_for_share` stops taking FOR SHARE (plan P8). A new file still waits on
    # the foreign key's KEY SHARE, so only the same file signed again, which inserts nothing,
    # shows the subject lock missing: a fresh URL into a subject being deleted.
    with Session(engine) as setup:
        pending_document(setup, account, datetime.now(UTC) - timedelta(minutes=10))
        setup.commit()
    with Session(engine) as deleter, Session(engine) as uploading:
        SubjectRepository(deleter, account.user_id).soft_delete(
            account.subject_id, datetime.now(UTC)
        )
        uploading.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(OperationalError) as refused:
            pending_document(uploading, account, datetime.now(UTC))
        assert getattr(refused.value.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE
        uploading.rollback()
        deleter.rollback()


def test_a_confirm_waits_while_the_subject_is_being_deleted_then_announces_nothing(
    engine: Engine, account: Account, app_client: TestClient, fake_storage: FakeStorage
) -> None:
    # Red when: confirm skips `hold_for_share` (plan P9): it would announce a file of a subject
    # whose deletion commits a moment later.
    with Session(engine) as setup:
        document_id = pending_document(setup, account, datetime.now(UTC)).id
        object_key = setup.get_one(Document, document_id).object_key
        setup.commit()
    fake_storage.put(object_key, PDF, PDF_SHA_B64)

    with Session(engine) as deleter:
        SubjectRepository(deleter, account.user_id).soft_delete(
            account.subject_id, datetime.now(UTC)
        )
        deleter_pid = deleter.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(
            lambda: app_client.post(f"/v1/documents/{document_id}/confirm", headers=account.headers)
        )
        wait_until_blocked_by(engine, deleter_pid, outcome)
        deleter.commit()
    response = finished(thread, outcome)

    assert isinstance(response, Response), response
    assert (response.status_code, response.json()) == (404, {"detail": "subject_not_found"})
    with Session(engine) as session:
        assert session.get_one(Document, document_id).status == "pending"
        events = session.scalars(select(Outbox).where(Outbox.user_id == account.user_id)).all()
        assert events == []


def test_the_cleanup_job_waits_document_cleanup_after_seconds_not_the_urls_life(
    engine: Engine, account: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Red when: the job reads its age from another setting (s3_presign_seconds: rows deleted
    # while their URL still works), or does not commit what it deleted.
    settings = get_settings()
    now = datetime.now(UTC)
    between = now - timedelta(seconds=settings.document_cleanup_after_seconds // 2)
    long_ago = now - timedelta(seconds=settings.document_cleanup_after_seconds + 120)
    assert between < now - timedelta(seconds=settings.s3_presign_seconds)
    with Session(engine) as setup:
        recent = pending_document(setup, account, between)
        other, _ = SubjectRepository(setup, account.user_id).create_with_exam(
            "Toán", future_exam(60)
        )
        setup.flush()
        old, _ = DocumentRepository(setup, account.user_id).reserve(
            other.id,
            sha256="ab" * 32,
            size_bytes=10,
            short_name="Cũ",
            now=long_ago,
            quota_bytes=10**12,
            global_quota_bytes=10**15,
        )
        ids = (recent.id, old.id)
        setup.commit()
    storage = FakeStorage()

    class FakeS3:
        @staticmethod
        def from_settings(_: object) -> FakeStorage:
            return storage

    monkeypatch.setattr(document_cleanup, "S3Storage", FakeS3)
    monkeypatch.setattr(document_cleanup, "get_engine", lambda: engine)

    document_cleanup.document_cleanup_job({})

    with Session(engine) as session:
        assert session.get(Document, ids[0]) is not None
        assert session.get(Document, ids[1]) is None
    assert any(key.endswith(f"{'ab' * 32}.pdf") for key in storage.deleted)


def test_a_confirm_failing_after_the_event_is_queued_leaves_no_event(
    engine: Engine,
    account: Account,
    app_client: TestClient,
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: the event is committed apart from the request's transaction, even after
    # `enqueue_event` returns (test_documents_e2e only fails inside it): an event for a document
    # still pending, which ai-service would process while the user is told to confirm again.
    with Session(engine) as setup:
        document = pending_document(setup, account, datetime.now(UTC))
        document_id, object_key = document.id, document.object_key
        setup.commit()
    fake_storage.put(object_key, PDF, PDF_SHA_B64)

    def crash(_: Document) -> None:
        raise RuntimeError("crash after the event, before the commit")

    monkeypatch.setattr(documents_api, "_out", crash)
    path = f"/v1/documents/{document_id}/confirm"
    assert app_client.post(path, headers=account.headers).status_code == 500

    with Session(engine) as session:
        assert session.get_one(Document, document_id).status == "pending"
        events = session.scalars(select(Outbox).where(Outbox.user_id == account.user_id)).all()
        assert events == []


def test_a_confirm_behind_another_confirm_announces_nothing_more(
    engine: Engine, account: Account, app_client: TestClient, fake_storage: FakeStorage
) -> None:
    # Red when: confirm reads the row without `lock` (FOR UPDATE, read afresh): it would check
    # the file while the other confirm holds the row, then mark it uploaded and queue a second
    # `document.uploaded.v1` once the other commits.
    with Session(engine) as setup:
        document = pending_document(setup, account, datetime.now(UTC))
        document_id, object_key = document.id, document.object_key
        setup.commit()
    fake_storage.put(object_key, PDF, PDF_SHA_B64)

    with Session(engine) as other_confirm:
        held = DocumentRepository(other_confirm, account.user_id).lock(document_id)
        assert held is not None
        other_pid = other_confirm.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(
            lambda: app_client.post(f"/v1/documents/{document_id}/confirm", headers=account.headers)
        )
        wait_until_blocked_by(engine, other_pid, outcome)
        # The other confirm wins; its event is not this test's concern.
        held.status, held.uploaded_at = "uploaded", datetime.now(UTC)
        other_confirm.commit()
    response = finished(thread, outcome)

    assert isinstance(response, Response), response
    assert (response.status_code, response.json()["status"]) == (200, "uploaded")
    with Session(engine) as session:
        events = session.scalars(select(Outbox).where(Outbox.user_id == account.user_id)).all()
        assert events == []


def test_a_confirm_that_waited_for_the_row_sees_it_as_the_other_left_it(
    engine: Engine, account: Account
) -> None:
    # Red when: `lock` drops populate_existing. Confirm reads the row (`get`) before it locks
    # it, so the session already holds it as pending; a confirm that committed meanwhile would
    # be overlooked, and the file announced twice.
    with Session(engine) as setup:
        document_id = pending_document(setup, account, datetime.now(UTC)).id
        setup.commit()
    with Session(engine) as first, Session(engine) as second:
        winner = DocumentRepository(first, account.user_id).lock(document_id)
        assert winner is not None
        first_pid = first.execute(text("SELECT pg_backend_pid()")).scalar_one()
        late = DocumentRepository(second, account.user_id)
        seen = late.get(document_id)
        assert seen is not None and seen.status == "pending"
        thread, outcome = in_thread(lambda: late.lock(document_id))
        wait_until_blocked_by(engine, first_pid, outcome)
        winner.status, winner.uploaded_at = "uploaded", datetime.now(UTC)
        first.commit()
        locked = finished(thread, outcome)
        assert isinstance(locked, Document), locked
        assert locked.status == "uploaded"
        second.rollback()
