"""US-14: a question bank that ai-service has read is split without the learner asking again.

The upload step only says "Đã đọc xong"; nothing called the import route, so the bank never
reached practice. `document.indexed.v1` now queues the import for a `question_bank` document.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.handlers.document_indexed import OnDocumentIndexed
from documents.test_document_indexed import indexed_event, uploaded
from fake_storage import FakeStorage


def jobs(session: Session, document_id: object) -> int:
    return session.execute(
        text(
            "SELECT count(*) FROM procrastinate_jobs"
            " WHERE task_name = 'question_bank_import'"
            " AND args->'payload'->>'document_id' = :d"
        ),
        {"d": str(document_id)},
    ).scalar_one()


def test_indexed_bank_queues_one_import(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user, "uploaded")
    document.role = "question_bank"
    event = indexed_event(document, None, payload={"page_count": 40})
    OnDocumentIndexed(FakeStorage())(db_session, event)
    OnDocumentIndexed(FakeStorage())(db_session, event)  # a re-run of the same answer
    db_session.flush()
    assert jobs(db_session, document.id) == 1


def test_indexed_textbook_queues_none(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user, "uploaded")
    event = indexed_event(document, None, payload={"page_count": 40})
    OnDocumentIndexed(FakeStorage())(db_session, event)
    db_session.flush()
    assert jobs(db_session, document.id) == 0
