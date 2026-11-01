"""A user with a subject, a document, a section, a draft study session and a submission, with
builders of the v2 result file and its events (T7.8). Storage is a double; the database is real."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from core_api.db.models import DocSection, Document, StudySession, Subject, Submission, User
from core_api.handlers.session_result_v2 import result_key_for
from core_api.messaging.envelope import Event, parse_event
from core_api.messaging.session_result_v2 import draft_key, quote_hash
from fake_storage import FakeStorage
from sessions.session_helpers import indexed_document, subject_of
from v2_rows import make_section

RUN = uuid.uuid4()
NOW = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)


class World:
    def __init__(self, db: Session, user: User, storage: FakeStorage) -> None:
        self.db, self.user, self.storage = db, user, storage
        self.subject: Subject = subject_of(db, user)
        self.document: Document = indexed_document(db, storage, user, self.subject)
        self.section: DocSection = make_section(db, user, self.document, ord=0)
        self.section2: DocSection = make_section(db, user, self.document, ord=1, title="Chương 2")
        self.study = StudySession(
            user_id=user.id,
            subject_id=self.subject.id,
            description_raw="học chương 3",
            extraction="proposed",
            status="draft",
        )
        db.add(self.study)
        db.flush()
        self.submission = Submission(
            user_id=user.id, session_id=self.study.id, status="processing", file_keys=[]
        )
        db.add(self.submission)
        db.flush()

    def draft(self, n: int, **over: Any) -> dict[str, Any]:
        quote = f"Câu trích số {n}."
        qh = quote_hash(quote)
        base: dict[str, Any] = {
            "draft_key": draft_key(self.study.id, qh),
            "quote_hash": qh,
            "title": f"Thẻ {n}",
            "content": f"Nội dung {n}.",
            "kind": "concept",
            "section_id": str(self.section.id),
            "suggested_section_id": None,
            "anchors": [
                {
                    "source": "document",
                    "document_id": str(self.document.id),
                    "page_no": 3,
                    "start": 0,
                    "end": len(quote),
                    "quote_text": quote,
                }
            ],
        }
        return base | over

    def body(self, drafts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "version": 2,
            "study_session_id": str(self.study.id),
            "drafts": drafts,
            "dropped": {"anchors": 0, "drafts": 0},
            "skipped": [],
        }

    def key(self) -> str:
        return result_key_for(self.user.id, self.study.id, self.submission.id)

    def put(self, drafts: list[dict[str, Any]]) -> str:
        key = self.key()
        self.storage.write(
            key, json.dumps(self.body(drafts), ensure_ascii=False).encode(), content_type="x"
        )
        return key

    def processed(self, key: str, *, user: User | None = None) -> Event:
        return parse_event(
            json.dumps(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "submission.processed.v1",
                    "schema_version": 1,
                    "occurred_at": "2026-11-01T03:00:00.000000Z",
                    "user_id": str((user or self.user).id),
                    "trace_context": {},
                    "payload": {
                        "submission_id": str(self.submission.id),
                        "study_session_id": str(self.study.id),
                        "run_id": str(RUN),
                        "result_key": key,
                    },
                }
            )
        )

    def failed(self, reason: str) -> Event:
        return parse_event(
            json.dumps(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "submission.failed.v1",
                    "schema_version": 1,
                    "occurred_at": "2026-11-01T03:00:00.000000Z",
                    "user_id": str(self.user.id),
                    "trace_context": {},
                    "payload": {
                        "submission_id": str(self.submission.id),
                        "study_session_id": str(self.study.id),
                        "run_id": str(RUN),
                        "reason": reason,
                    },
                }
            )
        )
