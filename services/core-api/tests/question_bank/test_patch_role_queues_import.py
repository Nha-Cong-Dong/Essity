"""QA 05/11 (US-14): a file already read as auxiliary, then put in the "Bộ câu hỏi" tab.

The upload dedupes by hash, so the file is not read again and `document.indexed.v1` never
queues the split. Changing the role to `question_bank` on a read document queues it.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import Document
from core_api.handlers.document_indexed import OnDocumentIndexed
from documents.test_document_indexed import indexed_event, uploaded
from fake_storage import FakeStorage


def jobs(session: Session, document_id: uuid.UUID) -> int:
    return session.execute(
        text(
            "SELECT count(*) FROM procrastinate_jobs"
            " WHERE task_name = 'question_bank_import'"
            " AND args->'payload'->>'document_id' = :d"
        ),
        {"d": str(document_id)},
    ).scalar_one()


def read_auxiliary(session: Session) -> tuple[Document, dict[str, str]]:
    user, headers = signed_in(session)
    document = uploaded(session, user, "uploaded")
    OnDocumentIndexed(FakeStorage())(
        session, indexed_event(document, None, payload={"page_count": 40})
    )
    session.flush()
    assert document.status == "indexed" and document.role == "auxiliary"
    return document, headers


def test_role_change_on_a_read_document_queues_one_import(
    client: TestClient, db_session: Session
) -> None:
    document, headers = read_auxiliary(db_session)

    for _ in range(2):  # a repeat asks again, still one waiting job
        response = client.patch(
            f"/v1/documents/{document.id}", json={"role": "question_bank"}, headers=headers
        )
        assert response.status_code == 200
    assert jobs(db_session, document.id) == 1


def test_other_role_changes_queue_none(client: TestClient, db_session: Session) -> None:
    document, headers = read_auxiliary(db_session)

    response = client.patch(
        f"/v1/documents/{document.id}", json={"role": "textbook"}, headers=headers
    )
    assert response.status_code == 200
    assert jobs(db_session, document.id) == 0
