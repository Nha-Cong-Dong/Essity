"""Reference documents of a subject (US-01, T4.5, ADR-0012).

The browser uploads straight to object storage: core-api signs a PUT for one PDF of a declared
size and SHA-256, at `users/{user}/subjects/{subject}/raw/{sha256}.pdf`, valid for a few minutes
and only to create (`If-None-Match: *`). The URL's headers must be sent as given; a PUT
answered 412 means the file is already there: confirm it.

Nothing about the file is logged, not its name, key or SHA-256, and never the URL (ADR-0013).
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from core_api.api.deps import Now, Storage, VerifiedUser, verified_user
from core_api.api.text import storable_text
from core_api.clients.storage import ObjectStorage, StorageUnavailableError
from core_api.config import get_settings
from core_api.db.models import Document
from core_api.db.models.document import UNCONFIRMED
from core_api.db.session import DbSession
from core_api.domain.documents import (
    PDF_MAGIC,
    InvalidFilenameError,
    UnsupportedFileTypeError,
    looks_like_pdf,
    short_name,
)
from core_api.messaging.envelope import DocumentUploaded
from core_api.messaging.outbox import enqueue_event
from core_api.repositories.document import (
    DocumentRejectedError,
    DocumentRepository,
    QuotaExceededError,
    SizeMismatchError,
    StorageFullError,
)
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.security.rate_limit import RateLimit, RateLimiter, get_rate_limiter

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

PDF = "application/pdf"
FILENAME_MAX = 255

Filename = Annotated[
    StrictStr, Field(min_length=1, max_length=FILENAME_MAX), AfterValidator(storable_text)
]
Sha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$"), AfterValidator(storable_text)]


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Filename
    size_bytes: StrictInt = Field(gt=0)
    sha256: Sha256  # lowercase hex of the file's SHA-256


class DocumentOut(BaseModel):
    id: uuid.UUID
    subject_id: uuid.UUID
    short_name: str
    status: str
    size_bytes: int
    created_at: datetime
    # From ai-service (T4.8): set once indexed (page_count) or failed (failure_reason).
    page_count: int | None
    unreadable_pages: list[int]
    failure_reason: str | None


class UploadUrl(BaseModel):
    url: str
    method: Literal["PUT"] = "PUT"
    # Send exactly these with the body; the body must be exactly `size_bytes` long.
    headers: dict[str, str]
    expires_at: datetime


class UploadOut(BaseModel):
    document: DocumentOut
    upload: UploadUrl | None  # None: the file is already uploaded, nothing to send
    duplicate: bool


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        subject_id=document.subject_id,
        short_name=document.short_name,
        status=document.status,
        size_bytes=document.size_bytes,
        created_at=document.created_at,
        page_count=document.page_count,
        unreadable_pages=document.unreadable_pages,
        failure_reason=document.failure_reason,
    )


@router.post(
    "/subjects/{subject_id}/documents",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": UploadOut, "description": "The file is already in the subject"}},
)
def request_upload(
    subject_id: uuid.UUID,
    body: UploadRequest,
    user: VerifiedUser,
    session: DbSession,
    storage: Storage,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    now: Now,
    response: Response,
) -> UploadOut:
    """A URL to upload one PDF to the subject (201), or the document it already is (200).

    The same file (SHA-256) again: uploaded → `duplicate: true` and no URL; still uploading →
    a fresh URL for the same document. Errors: 404 `subject_not_found`; 422
    `unsupported_file_type`, `invalid_filename`, `file_too_large`, `size_mismatch` (the same
    file asked with another size), `content_mismatch` (the same file was refused before); 409
    `storage_quota_exceeded`; 429 with Retry-After; 503 `storage_full` or when a dependency is
    down.
    """
    settings = get_settings()
    response.headers["Cache-Control"] = "no-store"
    # Every ask counts, a fresh URL for the same file too (plan D6).
    limiter.enforce(
        RateLimit("document_upload", settings.document_uploads_per_hour, timedelta(hours=1)),
        str(user.id),
    )
    try:
        name = short_name(body.filename)
    except UnsupportedFileTypeError:
        raise _error(422, "unsupported_file_type") from None
    except InvalidFilenameError:
        raise _error(422, "invalid_filename") from None
    if body.size_bytes > settings.document_max_bytes:
        raise _error(422, "file_too_large")

    try:
        document, created = DocumentRepository(session, user.id).reserve(
            subject_id,
            sha256=body.sha256,
            size_bytes=body.size_bytes,
            short_name=name,
            now=now,
            quota_bytes=settings.document_quota_bytes,
            global_quota_bytes=settings.storage_global_quota_bytes,
        )
    except SubjectNotFoundError:
        raise _error(404, "subject_not_found") from None
    except SizeMismatchError:
        raise _error(422, "size_mismatch") from None
    except DocumentRejectedError:
        raise _error(422, "content_mismatch") from None
    except QuotaExceededError:
        raise _error(409, "storage_quota_exceeded") from None
    except StorageFullError:
        raise _error(503, "storage_full") from None

    if not created:
        response.status_code = status.HTTP_200_OK
    if document.status not in UNCONFIRMED:
        return UploadOut(document=_out(document), upload=None, duplicate=True)
    signed = storage.presign_put(
        document.object_key,
        size=document.size_bytes,
        sha256=document.sha256,
        content_type=PDF,
        expires_in=settings.s3_presign_seconds,
    )
    return UploadOut(
        document=_out(document),
        upload=UploadUrl(
            url=signed.url,
            headers=signed.headers,
            expires_at=now + timedelta(seconds=settings.s3_presign_seconds),
        ),
        duplicate=False,
    )


def _check(storage: ObjectStorage, document: Document) -> str | None:
    """Why the stored file is not the PDF declared, or None when it is. HTTPException 409 when
    nothing is stored yet; StorageUnavailableError when the store does not answer."""
    stored = storage.head(document.object_key)
    if stored is None:
        raise _error(409, "upload_incomplete")
    if stored.size != document.size_bytes:
        return "size_mismatch"
    # None: the store keeps no SHA-256 for it; ai-service recomputes it (T4.7, plan P11).
    if stored.sha256 is not None and stored.sha256 != document.sha256:
        return "content_mismatch"
    if not looks_like_pdf(storage.read_start(document.object_key, len(PDF_MAGIC))):
        return "content_mismatch"
    return None


@router.post(
    "/documents/{document_id}/confirm",
    response_model=DocumentOut,
    responses={422: {"description": "The file stored is not the PDF declared"}},
)
def confirm_upload(
    document_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    storage: Storage,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    now: Now,
) -> DocumentOut | JSONResponse:
    """The file is stored: check it, mark the document uploaded and announce it to ai-service
    (`document.uploaded.v1`, in the same transaction). Confirming again changes nothing.

    Errors: 404 `document_not_found` (another user's too) or `subject_not_found` (deleted since);
    409 `upload_incomplete` (nothing stored yet: upload, or ask for a new URL, then confirm);
    422 `size_mismatch` or `content_mismatch`: the file is deleted and the document stays
    refused, so the same file cannot be uploaded again; 503 `storage_unavailable`.

    Locks the subject FOR SHARE, then the document FOR UPDATE: the order `reserve` takes them.
    Limited per account (429): each confirm calls the store.
    """
    limiter.enforce(
        RateLimit(
            "document_confirm", get_settings().document_confirms_per_hour, timedelta(hours=1)
        ),
        str(user.id),
    )
    documents = DocumentRepository(session, user.id)
    found = documents.get(document_id)
    if found is None:
        raise _error(404, "document_not_found")
    try:
        SubjectRepository(session, user.id).hold_for_share(found.subject_id)
    except SubjectNotFoundError:
        raise _error(404, "subject_not_found") from None
    document = documents.lock(document_id)
    if document is None:  # cleaned up in between
        raise _error(404, "document_not_found")
    if document.status not in UNCONFIRMED:
        return _out(document)
    if document.status == "rejected":
        return JSONResponse({"detail": "content_mismatch"}, status_code=422)

    try:
        problem = _check(storage, document)
        if problem is not None:
            # Deleted first: if that fails the row stays pending, for cleanup to retry.
            storage.delete(document.object_key)
    except StorageUnavailableError:
        raise _error(503, "storage_unavailable") from None
    if problem is not None:
        # A response, not an exception: the session commits the refusal (plan R1).
        document.status = "rejected"
        return JSONResponse({"detail": problem}, status_code=422)

    document.status = "uploaded"
    document.uploaded_at = now
    enqueue_event(
        session,
        DocumentUploaded(
            document_id=document.id,
            subject_id=document.subject_id,
            object_key=document.object_key,
        ),
        user_id=user.id,
        now=now,
    )
    return _out(document)


@router.get("/subjects/{subject_id}/documents", response_model=list[DocumentOut])
def list_documents(
    subject_id: uuid.UUID, user: VerifiedUser, session: DbSession, response: Response
) -> list[DocumentOut]:
    """The subject's documents, oldest first (T4.9). Errors: 404 `subject_not_found` (another
    user's too)."""
    response.headers["Cache-Control"] = "no-store"
    if SubjectRepository(session, user.id).get(subject_id) is None:
        raise _error(404, "subject_not_found")
    return [_out(d) for d in DocumentRepository(session, user.id).of_subject(subject_id)]


@router.get("/documents/{document_id}", response_model=DocumentOut)
def read_document(
    document_id: uuid.UUID, user: VerifiedUser, session: DbSession, response: Response
) -> DocumentOut:
    """One document with its processing status (T4.9). Errors: 404 `document_not_found`
    (another user's too)."""
    response.headers["Cache-Control"] = "no-store"
    document = DocumentRepository(session, user.id).get(document_id)
    if document is None:
        raise _error(404, "document_not_found")
    return _out(document)


# What ai-service writes at `toc_key`: a few hundred sections at most; more is not a table of
# contents core should relay.
TOC_MAX_BYTES = 1 << 20


class TocOut(BaseModel):
    document_id: uuid.UUID
    # The table of contents as ai-service wrote it (T4.7): sections with their page ranges.
    toc: Any


@router.get(
    "/documents/{document_id}/toc",
    response_model=TocOut,
    responses={409: {"description": "The document is not indexed (yet)"}},
)
def read_toc(
    document_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    storage: Storage,
    response: Response,
) -> TocOut:
    """The table of contents of an indexed document (US-02 AC2), read from its derived file.

    Errors: 404 `document_not_found` (another user's too); 409 `not_indexed`; 502 `toc_invalid`
    (the file is not JSON or too large); 503 `storage_unavailable`.
    """
    response.headers["Cache-Control"] = "no-store"
    document = DocumentRepository(session, user.id).get(document_id)
    if document is None:
        raise _error(404, "document_not_found")
    if document.status != "indexed" or document.toc_key is None:
        raise _error(409, "not_indexed")
    try:
        raw = storage.read_start(document.toc_key, TOC_MAX_BYTES + 1)
    except StorageUnavailableError:
        raise _error(503, "storage_unavailable") from None
    try:
        if len(raw) > TOC_MAX_BYTES:
            raise ValueError
        toc = json.loads(raw)
    except ValueError:
        raise _error(502, "toc_invalid") from None
    return TocOut(document_id=document.id, toc=toc)
