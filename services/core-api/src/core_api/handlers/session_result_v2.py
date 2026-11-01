"""`submission.processed.v1` and `submission.failed.v1` (T7.8, US-02b AC1, AC10, AC13): the drafts
ai-service made from a submission become draft cards, written in the consumer's transaction.

The consumer has claimed the event. Nothing else in it or in the file is trusted:

- The study session must be the user's; it is locked first (the one lock order of every review
  write, `DraftRepository`). The submission must be that session's and not done already.
- The result key is rebuilt from the locked submission and compared whole; the file is read with a
  size cap, parsed against the closed model and must name this very session.
- Ids in the file only point at things: a document or section that is not the subject's drops the
  anchor or the link, a draft with no valid anchor left is dropped, and the rest is written.
- A draft is inserted with ON CONFLICT (session_id, draft_key) DO NOTHING: a resent result, a new
  event over the same file, a card the learner retired, never make a second card or bring one
  back. The AI's own version is stored as revision 0 (origin `ai`) and never rewritten.

`submission.failed.v1` with `llm_unavailable` parks the submission as `pending_ai` (the retry job
is T7.8b); any other reason ends it as `failed`. A submission already done is never moved back.

Logs hold ids and counts, never a title, a quote or a key (ADR-0013).
"""

import logging
import uuid

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.clients.storage import ObjectStorage
from core_api.db.models import Anchor as AnchorRow
from core_api.db.models import DocSection, Submission
from core_api.messaging.envelope import Event, SubmissionFailedEvent, SubmissionProcessedEvent
from core_api.messaging.session_result_v2 import Anchor, Draft, SessionResultV2, parse_result
from core_api.repositories.document import DocumentRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.submission import SubmissionRepository
from core_api.repositories.unit import DraftRepository

_log = logging.getLogger("core_api.handlers")
# The writer's own cap (ai-service `process_submission`): a file it may write is a file this reads.
MAX_RESULT_BYTES = 8_000_000
ENDED = frozenset({"done", "failed"})


def result_key_for(
    user_id: uuid.UUID, study_session_id: uuid.UUID, submission_id: uuid.UUID
) -> str:
    return f"users/{user_id}/sessions/{study_session_id}/result-{submission_id}.json"


def revision_content(title: str, content: str, kind: str) -> dict[str, str]:
    return {"title": title, "content": content, "kind": kind}


class OnSubmissionProcessed:
    def __init__(self, storage: ObjectStorage) -> None:
        self.storage = storage

    def __call__(self, session: Session, event: Event) -> None:
        assert isinstance(event, SubmissionProcessedEvent)
        payload, user_id = event.payload, event.user_id
        extra = {
            "event_id": str(event.event_id),
            "study_session_id": str(payload.study_session_id),
            "submission_id": str(payload.submission_id),
        }
        drafts = DraftRepository(session, user_id)
        study = drafts.lock_session(payload.study_session_id)
        submission = SubmissionRepository(session, user_id).get(payload.submission_id)
        if study is None or submission is None or submission.session_id != study.id:
            _log.warning("submission result ignored", extra=extra | {"found": study is not None})
            return
        if submission.status == "done":
            _log.info("submission result ignored", extra=extra | {"reason": "done"})
            return
        if SubjectRepository(session, user_id).get(study.subject_id) is None:
            _log.warning("submission result ignored", extra=extra | {"reason": "subject_gone"})
            return
        if payload.result_key != result_key_for(user_id, study.id, submission.id):
            _log.error("submission result refused", extra=extra | {"reason": "key"})
            _end(submission, "failed", event)
            return
        raw = self.storage.read(payload.result_key, max_bytes=MAX_RESULT_BYTES)  # raises: retried
        if raw is None:
            _log.warning("submission result missing", extra=extra)
            _end(submission, "failed", event)
            return
        try:
            parsed = parse_result(raw)
        except ValidationError:  # its errors echo the input: never logged
            _log.error("submission result refused", extra=extra | {"reason": "schema"})
            _end(submission, "failed", event)
            return
        if parsed.study_session_id != study.id:
            _log.error("submission result refused", extra=extra | {"reason": "session"})
            _end(submission, "failed", event)
            return
        written = _write(session, drafts, study.subject_id, study.id, payload.run_id, parsed)
        _end(submission, "done", event)
        _log.info("submission result written", extra=extra | written)


def _end(submission: Submission, status: str, event: Event) -> None:
    submission.status = status
    submission.finished_at = event.occurred_at


def _write(
    session: Session,
    drafts: DraftRepository,
    subject_id: uuid.UUID,
    study_session_id: uuid.UUID,
    run_id: uuid.UUID,
    parsed: SessionResultV2,
) -> dict[str, int]:
    user_id = drafts.user_id
    documents = {d.id for d in DocumentRepository(session, user_id).of_subject(subject_id)}
    sections = set(
        session.scalars(
            select(DocSection.id).where(
                DocSection.user_id == user_id, DocSection.subject_id == subject_id
            )
        )
    )
    added = skipped = dropped = 0
    for draft in parsed.drafts:
        anchors = [a for a in draft.anchors if _anchor_ok(a, documents)]
        if not anchors:
            dropped += 1
            continue
        wanted = draft.section_ids if draft.section_ids is not None else _single(draft)
        linked = [s for s in wanted if s in sections]
        unit_id = drafts.insert_draft(
            subject_id=subject_id,
            session_id=study_session_id,
            draft_key=draft.draft_key,
            title=draft.title,
            summary=draft.content,
            kind=draft.kind,
            section_id=linked[0] if linked else None,
            run_id=run_id,
        )
        if unit_id is None:
            skipped += 1
            continue
        drafts.add_revision(
            unit_id, 0, "ai", revision_content(draft.title, draft.content, draft.kind)
        )
        for found in anchors:
            session.add(_anchor_row(user_id, unit_id, found, run_id))
        drafts.add_sections(unit_id, subject_id, linked)
        added += 1
    session.flush()
    return {"drafts": added, "already_there": skipped, "dropped_drafts": dropped}


def _single(draft: Draft) -> list[uuid.UUID]:
    return [draft.section_id] if draft.section_id is not None else []


def _anchor_ok(found: Anchor, documents: set[uuid.UUID]) -> bool:
    if not found.quote_text.strip() or found.end < found.start:
        return False
    if found.source == "document":
        return found.document_id is not None and found.document_id in documents
    return found.document_id is None


def _anchor_row(
    user_id: uuid.UUID, unit_id: uuid.UUID, found: Anchor, run_id: uuid.UUID
) -> AnchorRow:
    return AnchorRow(
        user_id=user_id,
        unit_id=unit_id,
        source=found.source,
        document_id=found.document_id,
        page_no=found.page_no,
        char_start=found.start,
        char_end=found.end,
        quote_text=found.quote_text,
        run_id=run_id,
    )


def on_submission_failed(session: Session, event: Event) -> None:
    assert isinstance(event, SubmissionFailedEvent)
    payload, user_id = event.payload, event.user_id
    extra = {
        "event_id": str(event.event_id),
        "study_session_id": str(payload.study_session_id),
        "submission_id": str(payload.submission_id),
    }
    drafts = DraftRepository(session, user_id)
    study = drafts.lock_session(payload.study_session_id)
    submission = SubmissionRepository(session, user_id).get(payload.submission_id)
    if study is None or submission is None or submission.session_id != study.id:
        _log.warning("submission failure ignored", extra=extra)
        return
    if submission.status in ENDED:
        return
    if payload.reason == "llm_unavailable":
        if submission.status in {"queued", "processing"}:
            submission.status = "pending_ai"
        return
    _end(submission, "failed", event)
    _log.info("submission failed", extra=extra | {"reason": payload.reason})
