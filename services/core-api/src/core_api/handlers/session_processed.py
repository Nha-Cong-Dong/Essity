"""`session.processed.v1` (T4.17, US-02 AC13): ai-service's units, anchors and questions for a
confirmed study session, written in the consumer's transaction.

The consumer has claimed the event (so it is handled once) and checked that the result key is under
the event's user (F2). Here nothing else in the event or the file is trusted:

- The session must be that user's and confirmed (`StudySessionRepository`, locked FOR UPDATE: two
  events on one session run one after the other).
- The key must be the session's own directory (`users/<u>/subjects/<s>/sessions/<id>/`) and a name
  `result-<uuid>.json`, derived from the locked session, not from the event and not from the
  outbox (its rows are cleaned after a week).
- The file is read with a size cap, parsed against a closed model, and cleaned (`domain/
  session_result.py`). A unit, anchor, question, merge or lineage row that breaks a rule is dropped
  and counted; the rest is written. Ids are the server's own: the file's ids only link its parts.
- A question whose prompt the subject already has is not added again, and is not linked to the new
  units (AC13, us-04b AC1).

A result that can never be written (a draft or foreign session, a key that is not the session's, a
file that is missing or breaks the contract) is logged and ends the event: it is claimed, so it is
not retried. The storage not answering raises: the consumer retries with backoff.

Logs hold ids and counts, never a title, a prompt or a key (ADR-0013).
"""

import logging
import re
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from core_api.clients.storage import ObjectStorage
from core_api.db.models import StudySession
from core_api.domain.session_result import (
    CleanAnchor,
    CleanMerge,
    CleanResult,
    ResultRefused,
    clean,
    parse_result,
)
from core_api.handlers.session_progress import mark_failed, mark_processed
from core_api.messaging.envelope import Event, SessionProcessedEvent
from core_api.repositories.document import DocumentRepository
from core_api.repositories.question import (
    QuestionConflictError,
    QuestionRepository,
    QuestionRetiredError,
    QuestionUnitRepository,
)
from core_api.repositories.study_session import StudySessionRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import (
    AnchorRepository,
    KnowledgeUnitRepository,
    UnitLineageRepository,
)

_log = logging.getLogger("core_api.handlers")
# The writer's own cap (ai-service `process_session.MAX_RESULT_BYTES`): a file it may write is a
# file this reads.
MAX_RESULT_BYTES = 8_000_000
_RESULT_NAME = re.compile(
    r"result-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json"
)


class OnSessionProcessed:
    def __init__(self, storage: ObjectStorage) -> None:
        self.storage = storage

    def __call__(self, session: Session, event: Event) -> None:
        assert isinstance(event, SessionProcessedEvent)
        payload, user_id = event.payload, event.user_id
        extra = {"event_id": str(event.event_id), "study_session_id": str(payload.study_session_id)}
        study = StudySessionRepository(session, user_id).lock(payload.study_session_id)
        if study is None or study.status != "confirmed":
            _log.warning("session result ignored", extra=extra | {"found": study is not None})
            return
        if SubjectRepository(session, user_id).get(study.subject_id) is None:
            _log.warning("session result ignored", extra=extra | {"reason": "subject_gone"})
            return
        if not _is_result_key(payload.result_key, study):
            _log.error("session result refused", extra=extra | {"reason": "key"})
            mark_failed(session, user_id, study.id, "internal_error")
            return
        raw = self.storage.read(payload.result_key, max_bytes=MAX_RESULT_BYTES)  # raises: retried
        if raw is None:
            _log.warning("session result missing", extra=extra)
            mark_failed(session, user_id, study.id, "internal_error")
            return
        try:
            parsed = parse_result(raw)
        except ValidationError:  # its errors echo the input: never logged
            _log.error("session result refused", extra=extra | {"reason": "schema"})
            mark_failed(session, user_id, study.id, "internal_error")
            return
        documents = {
            d.id for d in DocumentRepository(session, user_id).of_subject(study.subject_id)
        }
        try:
            cleaned = clean(parsed, study_session_id=study.id, documents=documents)
        except ResultRefused as refused:
            _log.error("session result refused", extra=extra | {"reason": str(refused)})
            mark_failed(session, user_id, study.id, "internal_error")
            return
        written = _write(session, study, payload.run_id, cleaned)
        mark_processed(session, user_id, study.id)
        _log.info("session result written", extra=extra | written)


def _is_result_key(key: str, study: StudySession) -> bool:
    prefix = f"users/{study.user_id}/subjects/{study.subject_id}/sessions/{study.id}/"
    return key.startswith(prefix) and _RESULT_NAME.fullmatch(key[len(prefix) :]) is not None


def _write(
    session: Session, study: StudySession, run_id: uuid.UUID, cleaned: CleanResult
) -> dict[str, int]:
    user_id, subject_id = study.user_id, study.subject_id
    units = KnowledgeUnitRepository(session, user_id)
    anchors = AnchorRepository(session, user_id)
    lineage = UnitLineageRepository(session, user_id)
    made: dict[uuid.UUID, uuid.UUID] = {}  # the file's unit id -> the row's
    lineage_count = 0
    for item in cleaned.units:
        row = units.create(
            subject_id, title=item.title, summary=item.summary, kind=item.kind, run_id=run_id
        )
        made[item.unit_id] = row.id
        for found in item.anchors:
            _add_anchor(anchors, row.id, found, run_id)
        for old_id in item.lineage:
            old = units.get(old_id)
            if old is not None and old.subject_id == subject_id:
                lineage.create(old.id, row.id, run_id)
                lineage_count += 1
    merged = _merge(units, anchors, subject_id, cleaned.merges, run_id)
    asked = _questions(session, study, run_id, cleaned, made)
    return {
        "units": len(made),
        "merges": merged,
        "lineage": lineage_count,
        "questions": asked,
        "dropped_units": cleaned.dropped_units,
        "dropped_anchors": cleaned.dropped_anchors,
        "dropped_questions": cleaned.dropped_questions + len(cleaned.questions) - asked,
    }


def _add_anchor(
    anchors: AnchorRepository, unit_id: uuid.UUID, found: CleanAnchor, run_id: uuid.UUID
) -> None:
    anchors.create(
        unit_id,
        source=found.source,
        document_id=found.document_id,
        page_no=found.page_no,
        char_start=found.start,
        char_end=found.end,
        quote_text=found.quote_text,
        run_id=run_id,
    )


def _merge(
    units: KnowledgeUnitRepository,
    anchors: AnchorRepository,
    subject_id: uuid.UUID,
    merges: list[CleanMerge],
    run_id: uuid.UUID,
) -> int:
    """New anchors on units the subject already has (active ones only); a quote the unit holds
    already is not added twice."""
    done = 0
    for merge in merges:
        unit = units.get(merge.existing_unit_id)
        if unit is None or unit.subject_id != subject_id or unit.status != "active":
            continue
        for found in merge.anchors:
            if not anchors.has_quote(unit.id, found.source, found.quote_text):
                _add_anchor(anchors, unit.id, found, run_id)
        done += 1
    return done


def _questions(
    session: Session,
    study: StudySession,
    run_id: uuid.UUID,
    cleaned: CleanResult,
    made: dict[uuid.UUID, uuid.UUID],
) -> int:
    questions = QuestionRepository(session, study.user_id)
    links = QuestionUnitRepository(session, study.user_id)
    added = 0
    for item in cleaned.questions:
        if questions.find_by_prompt(study.subject_id, item.prompt) is not None:
            continue  # the subject asks this already: the old question keeps its units (AC13)
        try:
            row = questions.add_idempotent(
                study.subject_id,
                level=item.level,
                prompt=item.prompt,
                reference_answer=item.reference_answer,
                rubric=item.rubric,
                run_id=run_id,
            )
        except (QuestionRetiredError, QuestionConflictError):
            continue
        for unit_id in item.unit_ids:
            links.link_once(row.id, made[unit_id])
        added += 1
    return added
