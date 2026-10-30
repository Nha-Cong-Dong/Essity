"""Note files of a draft session (US-02, T4.13b, ADR-0012): the learner's notebook photos.

The browser uploads straight to object storage, as for a PDF (`documents.py`): core-api signs a
PUT for one file of a declared type, size and SHA-256 at
`users/{user}/sessions/{session}/notes/{sha256}.{ext}`, valid for a few minutes and only to
create. `POST /v1/sessions/{id}/confirm` then looks at what arrived. A PUT answered 412 means the
file is already there: send it in the confirm.

Nothing about the file is logged, not its key or SHA-256, and never the URL (ADR-0013).
"""

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from core_api.api.deps import Now, Storage, VerifiedUser, verified_user
from core_api.api.text import storable_text
from core_api.config import get_settings
from core_api.db.session import DbSession
from core_api.domain.study_session import DOCX_MIME, PPTX_MIME
from core_api.repositories.note_upload import (
    BadNoteError,
    NoteQuotaExceededError,
    NoteUploadRepository,
    TooManyNotesError,
)
from core_api.repositories.study_session import StudySessionRepository
from core_api.security.rate_limit import RateLimit, RateLimiter, get_rate_limiter

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

Mime = Literal[
    "image/jpeg",
    "image/png",
    "application/pdf",
    "text/plain",
    "text/markdown",
    # v2 submissions only (T7.6): the v1 confirm still refuses them.
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
]
Sha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$"), AfterValidator(storable_text)]

SUBMISSION_ONLY_MIMES = frozenset({DOCX_MIME, PPTX_MIME})


class NoteUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: Sha256  # lowercase hex of the file's SHA-256
    mime: Mime
    size_bytes: StrictInt = Field(gt=0)


class NoteUploadUrl(BaseModel):
    url: str
    method: Literal["PUT"] = "PUT"
    # Send exactly these with the body; the body must be exactly `size_bytes` long.
    headers: dict[str, str]
    expires_at: datetime


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


@router.post(
    "/sessions/{session_id}/notes/upload-url",
    response_model=NoteUploadUrl,
    status_code=201,
    responses={200: {"model": NoteUploadUrl, "description": "A fresh URL for a file asked before"}},
)
def request_note_upload(
    session_id: uuid.UUID,
    body: NoteUploadRequest,
    user: VerifiedUser,
    session: DbSession,
    storage: Storage,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    now: Now,
    response: Response,
) -> NoteUploadUrl:
    """A URL to upload one note file of a draft session (201), or a fresh one for a file asked
    before (200).

    Errors: 404 `session_not_found` (another user's too); 409 `session_confirmed`,
    `too_many_notes`, `storage_quota_exceeded`; 422 `file_too_large`, `bad_note` (the same file
    asked with another type or size); 429 with Retry-After; 503 when a dependency is down.
    """
    settings = get_settings()
    response.headers["Cache-Control"] = "no-store"
    if body.mime in SUBMISSION_ONLY_MIMES and not settings.submissions_enabled:
        raise _error(422, "bad_note")
    # Every ask counts, a fresh URL for the same file too.
    limiter.enforce(
        RateLimit("note_upload", settings.note_uploads_per_hour, timedelta(hours=1)),
        str(user.id),
    )
    if body.size_bytes > settings.note_max_bytes:
        raise _error(422, "file_too_large")
    drafts = StudySessionRepository(session, user.id)
    draft = drafts.lock(session_id)
    if draft is None:
        raise _error(404, "session_not_found")
    if draft.status != "draft":
        raise _error(409, "session_confirmed")
    try:
        upload, created = NoteUploadRepository(session, user.id).reserve(
            session_id,
            sha256=body.sha256,
            mime=body.mime,
            size_bytes=body.size_bytes,
            now=now,
            quota_bytes=settings.note_quota_bytes,
        )
    except BadNoteError:
        raise _error(422, "bad_note") from None
    except TooManyNotesError:
        raise _error(409, "too_many_notes") from None
    except NoteQuotaExceededError:
        raise _error(409, "storage_quota_exceeded") from None

    if not created:
        response.status_code = 200
    signed = storage.presign_put(
        upload.object_key,
        size=upload.size_bytes,
        sha256=upload.sha256,
        content_type=upload.mime,
        expires_in=settings.s3_presign_seconds,
    )
    return NoteUploadUrl(
        url=signed.url,
        headers=signed.headers,
        expires_at=now + timedelta(seconds=settings.s3_presign_seconds),
    )
