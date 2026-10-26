"""Reference documents of a subject (US-01, T4.5, ADR-0012).

The browser uploads straight to object storage: core-api signs a PUT for one PDF of a declared
size and SHA-256, at `users/{user}/subjects/{subject}/raw/{sha256}.pdf`, valid for a few minutes
and only to create (`If-None-Match: *`). The URL's headers must be sent as given; a PUT
answered 412 means the file is already there: confirm it.

Nothing about the file is logged, not its name, key or SHA-256, and never the URL (ADR-0013).
"""

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from core_api.api.deps import Now, Storage, VerifiedUser, verified_user
from core_api.api.text import storable_text
from core_api.config import get_settings
from core_api.db.models import Document
from core_api.db.session import DbSession
from core_api.domain.documents import InvalidFilenameError, UnsupportedFileTypeError, short_name
from core_api.repositories.document import (
    DocumentRejectedError,
    DocumentRepository,
    QuotaExceededError,
    SizeMismatchError,
    StorageFullError,
)
from core_api.repositories.subject import SubjectNotFoundError
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
    if document.status == "uploaded":
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
