"""Handing in a study session, v2 (T7.6, US-02 AC2, AC3, AC4, AC11, AC13; spec v2 §16.3).

`POST /v1/subjects/{id}/submission-drafts` makes an empty draft session to upload files to (the
note upload route is the one v1 uses). `POST /v1/submissions` then takes the learner's
description, typed text and the files uploaded, in one transaction and in this order: everything
that can refuse (the `@mentions` against the documents' outlines, the files in the store), the
typed text written to the store, the context file written to the store, and only then the
`submission` row (status `queued`) with `submission.created.v1` in the outbox. A refusal writes
nothing.

The learner's words never go into the event or a log: they travel in the context file (ADR-0013).
The route is 404 while `submissions_enabled` is off (ai-service has no handler yet).
"""

import hashlib
import json
import uuid
from datetime import timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StrictStr
from sqlalchemy import func, select

from core_api.api.deps import Now, Storage, VerifiedUser, verified_user
from core_api.api.sessions import FILE_MAX_BYTES, _labels  # pyright: ignore[reportPrivateUsage]
from core_api.api.text import storable_answer, storable_text
from core_api.clients.storage import StorageUnavailableError
from core_api.config import get_settings
from core_api.db.models import DocSection, Document, NoteFile, NoteUpload, Submission
from core_api.db.models.study_session import DESCRIPTION_MAX, FILE_KEYS_MAX, SUBMISSION_MIMES
from core_api.db.session import DbSession
from core_api.domain.mention import (
    DocInfo,
    ExplicitMention,
    MentionError,
    ResolvedMention,
    SectionInfo,
    resolve_mentions,
)
from core_api.domain.study_session import NOTE_MAGIC_MAX, looks_like_note, note_key
from core_api.messaging.envelope import SubmissionCreated, SubmissionFile
from core_api.messaging.outbox import enqueue_event
from core_api.repositories.document import DocumentRepository
from core_api.repositories.note_upload import NoteUploadRepository
from core_api.repositories.study_session import StudySessionRepository
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.submission import SubmissionRepository
from core_api.repositories.unit import KnowledgeUnitRepository
from core_api.security.rate_limit import RateLimit, RateLimiter, get_rate_limiter

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

# The description of a draft that has none yet: the column is never blank.
PLACEHOLDER_DESCRIPTION = "(bài nộp)"
MAX_UNITS_IN_CONTEXT = 200
MAX_MENTION_DOCUMENTS = 12

Sha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$"), AfterValidator(storable_text)]


Typed = Annotated[StrictStr, AfterValidator(storable_answer)]


class FileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: Sha256
    mime: Literal[
        "image/jpeg",
        "image/png",
        "application/pdf",
        "text/plain",
        "text/markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ]
    size_bytes: StrictInt = Field(gt=0)


class MentionIn(BaseModel):
    """A mention the client already pointed at a document: `start` is the index of its `@`."""

    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID
    start: StrictInt = Field(ge=0, le=DESCRIPTION_MAX)
    end: StrictInt = Field(ge=1, le=DESCRIPTION_MAX)


class SubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID
    description: Typed | None = Field(default=None, max_length=DESCRIPTION_MAX)
    # Typed notes: the server stores them as a text file of the session.
    text: Typed | None = None
    files: list[FileIn] = Field(default=[], max_length=FILE_KEYS_MAX)
    mentions: list[MentionIn] = Field(default=[], max_length=20)


class MentionOut(BaseModel):
    document_id: uuid.UUID
    section_id: uuid.UUID | None
    first_page: int | None
    last_page: int | None


class SubmissionOut(BaseModel):
    submission_id: uuid.UUID
    session_id: uuid.UUID
    status: str
    mentions: list[MentionOut]


class DraftOut(BaseModel):
    session_id: uuid.UUID


def _error(code: int, detail: str | dict[str, Any]) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _enabled() -> None:
    if not get_settings().submissions_enabled:
        raise _error(404, "not_found")


def _mention_error(error: MentionError) -> HTTPException:
    detail: dict[str, Any] = {
        "code": error.code,
        "mention": error.mention,
        "part": error.part,
        "candidates": [str(c) for c in error.candidates],
    }
    return _error(422, detail)


@router.post(
    "/subjects/{subject_id}/submission-drafts",
    response_model=DraftOut,
    status_code=201,
    dependencies=[Depends(_enabled)],
    responses={404: {"description": "subject_not_found, or the feature is off"}},
)
def create_submission_draft(
    subject_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    response: Response,
) -> DraftOut:
    """An empty draft session to upload this submission's files to. Calls no AI."""
    response.headers["Cache-Control"] = "no-store"
    limiter.enforce(
        RateLimit("submission_draft", get_settings().session_creates_per_hour, timedelta(hours=1)),
        str(user.id),
    )
    try:
        draft = StudySessionRepository(session, user.id).create_draft(
            subject_id, PLACEHOLDER_DESCRIPTION
        )
    except SubjectNotFoundError:
        raise _error(404, "subject_not_found") from None
    return DraftOut(session_id=draft.id)


def _page_labels(storage: Storage, document: Document) -> list[str] | None:
    """The document's printed page labels. A store that fails is 503, never "no labels": a
    printed number must not be taken for a file position by mistake."""
    if document.page_labels_key is None:
        return None
    try:
        raw = storage.read_start(document.page_labels_key, FILE_MAX_BYTES + 1)
    except StorageUnavailableError:
        raise _error(503, "storage_unavailable") from None
    if len(raw) > FILE_MAX_BYTES:
        return None
    try:
        return _labels(json.loads(raw), document.page_count or 0)
    except ValueError:
        return None


def _documents(storage: Storage, documents: list[Document]) -> list[DocInfo]:
    """The indexed documents as the resolver reads them, labels always loaded."""
    return [
        DocInfo(d.id, d.short_name, d.format, d.page_count or 0, _page_labels(storage, d))
        for d in documents[:MAX_MENTION_DOCUMENTS]
    ]


def _resolve(
    body: SubmitRequest,
    documents: list[Document],
    repo: SubmissionRepository,
    storage: Storage,
) -> tuple[list[ResolvedMention], list[DocSection]]:
    description = body.description or ""
    infos = _documents(storage, documents)
    sections = repo.sections_of([d.id for d in infos])
    by_document: dict[uuid.UUID, list[SectionInfo]] = {}
    for s in sections:
        by_document.setdefault(s.document_id, []).append(
            SectionInfo(s.id, s.parent_id, s.ord, s.title, s.first_page, s.last_page)
        )
    explicit = [ExplicitMention(m.document_id, m.start, m.end) for m in body.mentions]
    known = {d.id for d in infos}
    if any(m.document_id not in known for m in body.mentions):
        raise _error(404, "document_not_found")
    try:
        resolved = resolve_mentions(description, infos, by_document, explicit)
    except MentionError as error:
        raise _mention_error(error) from None
    return resolved, sections


def _units_for_context(
    repo: SubmissionRepository,
    units: KnowledgeUnitRepository,
    subject_id: uuid.UUID,
    resolved: list[ResolvedMention],
    sections: list[DocSection],
) -> list[dict[str, str]]:
    """The existing units the AI merges with: those of the mentioned scope, or of the subject
    when nothing was mentioned."""
    if not resolved:
        found = units.for_event(subject_id, MAX_UNITS_IN_CONTEXT)
    else:
        children: dict[uuid.UUID | None, list[uuid.UUID]] = {}
        for s in sections:
            children.setdefault(s.parent_id, []).append(s.id)
        ids: set[uuid.UUID] = set()

        def add_tree(section_id: uuid.UUID) -> None:
            ids.add(section_id)
            for child in children.get(section_id, []):
                add_tree(child)

        for mention in resolved:
            if mention.section_id is not None:
                add_tree(mention.section_id)
            else:  # a whole document or a page range: every section of that document
                ids.update(s.id for s in sections if s.document_id == mention.document_id)
        found = repo.units_of_sections(subject_id, sorted(ids, key=str), MAX_UNITS_IN_CONTEXT)
    return [{"unit_id": str(u.id), "title": u.title, "summary": u.summary[:2000]} for u in found]


def _out(row: Submission, resolved: list[ResolvedMention]) -> SubmissionOut:
    return SubmissionOut(
        submission_id=row.id,
        session_id=row.session_id,
        status=row.status,
        mentions=[
            MentionOut(
                document_id=m.document_id,
                section_id=m.section_id,
                first_page=m.first_page,
                last_page=m.last_page,
            )
            for m in resolved
        ],
    )


@router.post(
    "/submissions",
    response_model=SubmissionOut,
    status_code=201,
    dependencies=[Depends(_enabled)],
    responses={
        200: {"model": SubmissionOut, "description": "The session was already submitted"},
        404: {"description": "session_not_found or document_not_found (another user's too)"},
        409: {"description": "session_confirmed, upload_incomplete or storage_quota_exceeded"},
        422: {
            "description": "A mention that does not resolve (`detail` names the part), nothing "
            "handed in, text_too_long, bad_note, size_mismatch or content_mismatch"
        },
    },
)
def submit(  # noqa: PLR0913, PLR0915
    body: SubmitRequest,
    user: VerifiedUser,
    session: DbSession,
    storage: Storage,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    now: Now,
    response: Response,
) -> SubmissionOut:
    """Store the submission and queue it for ai-service. Submitting a session again returns the
    first submission and announces nothing more.

    Errors: 404 `session_not_found`, `document_not_found`; 409 `session_confirmed`,
    `upload_incomplete`, `storage_quota_exceeded`; 422 a mention error (`detail` is an object
    with `code`, `mention`, `part`, `candidates`), `nothing_submitted`, `text_too_long`,
    `bad_note`, `size_mismatch`, `content_mismatch`; 429; 503 `storage_unavailable`.
    """
    settings = get_settings()
    response.headers["Cache-Control"] = "no-store"
    limiter.enforce(
        RateLimit("submission_create", settings.submissions_per_hour, timedelta(hours=1)),
        str(user.id),
    )
    drafts = StudySessionRepository(session, user.id)
    found = drafts.get(body.session_id)
    if found is None:
        raise _error(404, "session_not_found")
    try:
        SubjectRepository(session, user.id).hold_for_share(found.subject_id)
    except SubjectNotFoundError:
        raise _error(404, "session_not_found") from None
    draft = drafts.lock(body.session_id)
    if draft is None:
        raise _error(404, "session_not_found")
    submissions = SubmissionRepository(session, user.id)
    existing = submissions.of_session(draft.id)
    if existing is not None:
        response.status_code = 200
        return _out(existing, [])
    if draft.status != "draft":
        raise _error(409, "session_confirmed")

    # Everything that can refuse comes before the first write.
    typed = body.text.encode("utf-8") if body.text and body.text.strip() else None
    if typed is not None and len(typed) > settings.note_max_bytes:
        raise _error(422, "text_too_long")
    files: dict[str, FileIn] = {}
    for item in body.files:
        first = files.setdefault(item.sha256, item)
        if (first.mime, first.size_bytes) != (item.mime, item.size_bytes):
            raise _error(422, "bad_note")
    typed_sha = hashlib.sha256(typed).hexdigest() if typed is not None else None
    if typed is not None and typed_sha in files:
        declared = files[typed_sha]  # the typed text is never filed under another type or size
        if (declared.mime, declared.size_bytes) != ("text/plain", len(typed)):
            raise _error(422, "bad_note")
    if typed is not None and typed_sha is not None and typed_sha not in files:
        files[typed_sha] = FileIn(sha256=typed_sha, mime="text/plain", size_bytes=len(typed))
    if not files:
        raise _error(422, "nothing_submitted")
    if len(files) > FILE_KEYS_MAX or any(f.mime not in SUBMISSION_MIMES for f in files.values()):
        raise _error(422, "bad_note")

    documents = DocumentRepository(session, user.id).indexed_of_subject(
        draft.subject_id, MAX_MENTION_DOCUMENTS
    )
    resolved, sections = _resolve(body, documents, submissions, storage)
    keys = {sha: note_key(user.id, draft.id, sha, f.mime) for sha, f in files.items()}
    pending = NoteUploadRepository(session, user.id)
    held = pending.lock_of_session(draft.id, list(files))
    _check_stored(storage, files, keys, typed_sha)
    if _used_bytes(session, user.id) + (len(typed) if typed is not None else 0) > (
        settings.note_quota_bytes
    ):
        raise _error(409, "storage_quota_exceeded")

    written: list[str] = []
    try:
        if typed is not None and typed_sha is not None:
            storage.write(keys[typed_sha], typed, content_type="text/plain")
            written.append(keys[typed_sha])
        submission_id = uuid.uuid4()
        context_key = f"users/{user.id}/sessions/{draft.id}/context/{submission_id}.json"
        context = {
            "version": 1,
            "description": (body.description or "").strip() or None,
            "mentions": [
                {
                    "document_id": str(m.document_id),
                    "section_id": str(m.section_id) if m.section_id else None,
                    "first_page": m.first_page,
                    "last_page": m.last_page,
                }
                for m in resolved
            ],
            "existing_units": _units_for_context(
                submissions,
                KnowledgeUnitRepository(session, user.id),
                draft.subject_id,
                resolved,
                sections,
            ),
        }
        written.append(context_key)
        storage.write(
            context_key,
            json.dumps(context, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )
        for sha, item in files.items():
            session.add(
                NoteFile(
                    user_id=user.id,
                    session_id=draft.id,
                    object_key=keys[sha],
                    sha256=sha,
                    mime=item.mime,
                    size_bytes=item.size_bytes,
                )
            )
        for row in held:  # accounted by their note_file from now on
            session.delete(row)
        if body.description and body.description.strip():
            draft.description_raw = body.description.strip()
        row = Submission(
            id=submission_id,
            user_id=user.id,
            session_id=draft.id,
            status="queued",
            file_keys=[keys[sha] for sha in files],
        )
        session.add(row)
        session.flush()
        enqueue_event(
            session,
            SubmissionCreated(
                submission_id=submission_id,
                study_session_id=draft.id,
                subject_id=draft.subject_id,
                file_keys=[
                    SubmissionFile(object_key=keys[sha], mime=item.mime)  # pyright: ignore[reportArgumentType]
                    for sha, item in files.items()
                ],
                context_key=context_key,
            ),
            user_id=user.id,
            now=now,
        )
    except StorageUnavailableError:
        for key in written:
            _forget(storage, key)
        raise _error(503, "storage_unavailable") from None
    except BaseException:
        for key in written:
            _forget(storage, key)
        raise
    return _out(row, resolved)


def _used_bytes(session: DbSession, user_id: uuid.UUID) -> int:
    """The account's notes, stored and on their way: what the typed text is added to."""
    pending = session.scalar(
        select(func.coalesce(func.sum(NoteUpload.size_bytes), 0)).where(
            NoteUpload.user_id == user_id
        )
    )
    stored = session.scalar(
        select(func.coalesce(func.sum(NoteFile.size_bytes), 0)).where(NoteFile.user_id == user_id)
    )
    return int(pending or 0) + int(stored or 0)


def _forget(storage: Storage, key: str) -> None:
    try:
        storage.delete(key)
    except StorageUnavailableError:
        pass


def _check_stored(
    storage: Storage,
    files: dict[str, FileIn],
    keys: dict[str, str],
    typed_sha: str | None,
) -> None:
    """Each uploaded file is in the store, with the declared size and kind."""
    try:
        for sha, item in files.items():
            if sha == typed_sha:
                continue
            stored = storage.head(keys[sha])
            if stored is None:
                raise _error(409, "upload_incomplete")
            if stored.size != item.size_bytes:
                raise _error(422, "size_mismatch")
            if stored.sha256 is not None and stored.sha256 != sha:
                raise _error(422, "content_mismatch")
            start = storage.read_start(keys[sha], NOTE_MAGIC_MAX)
            if not looks_like_note(item.mime, start):
                raise _error(422, "content_mismatch")
    except StorageUnavailableError:
        raise _error(503, "storage_unavailable") from None
