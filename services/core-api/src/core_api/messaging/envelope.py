"""Event envelope and payloads (T4.1, ADR-0006), core-api's own copy of `contracts/events/`.

Not shared by import with ai-service (ADR-0003). `tests/test_event_contracts.py` checks that these
models accept exactly what the JSON Schemas accept, on every example in the contracts folder.
Payloads carry identifiers and object keys only (claim-check), never what a learner wrote.
"""

import re
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
)

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
UTC_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z$"
)
OBJECT_KEY_PATTERN = (
    r"^users/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"(/[A-Za-z0-9_][A-Za-z0-9._-]*)+$"
)
TRACEPARENT_PATTERN = r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"


def _canonical_uuid(value: Any) -> Any:
    # The schema takes only the lowercase hyphenated form; Pydantic's UUID alone takes more.
    if isinstance(value, str):
        if not UUID_PATTERN.match(value):
            raise ValueError("uuid must be lowercase and hyphenated")
        return UUID(value)
    return value


def _utc_timestamp(value: Any) -> Any:
    # Strict mode (no lax coercion elsewhere) means the string is parsed here.
    if isinstance(value, str):
        if not UTC_TIMESTAMP.match(value):
            raise ValueError("occurred_at must be UTC, ending in Z")
        return datetime.fromisoformat(value)
    return value


def _is_utc(value: datetime) -> datetime:
    # A producer passes a datetime: naive or another offset would be written without the Z.
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError("occurred_at must be timezone-aware UTC")
    return value


def _not_null(value: Any) -> Any:
    # An optional field may be absent but, as in the schema, never an explicit null.
    if value is None:
        raise ValueError("must not be null")
    return value


def _not_bool(value: Any) -> Any:
    # JSON `true` equals 1 in Python; the schema's `const: 1` rejects it.
    if isinstance(value, bool):
        raise ValueError("must be the integer 1")
    return value


Id = Annotated[UUID, BeforeValidator(_canonical_uuid)]
ObjectKey = Annotated[str, StringConstraints(max_length=1024, pattern=OBJECT_KEY_PATTERN)]
Page = Annotated[int, Field(ge=1, le=5000)]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class TraceContext(_Closed):
    traceparent: Annotated[
        str | None,
        BeforeValidator(_not_null),
        StringConstraints(pattern=TRACEPARENT_PATTERN),
    ] = None
    tracestate: Annotated[
        str | None, BeforeValidator(_not_null), StringConstraints(max_length=512)
    ] = None


# --- Payloads -------------------------------------------------------------------------------


class DocumentUploaded(_Closed):
    document_id: Id
    subject_id: Id
    object_key: ObjectKey


class DocumentIndexed(_Closed):
    document_id: Id
    run_id: Id
    page_count: Page
    toc_key: ObjectKey
    page_labels_key: ObjectKey
    page_text_key: ObjectKey
    thumbnails_prefix: ObjectKey
    unreadable_pages: Annotated[list[Page], Field(max_length=5000)]


class DocumentFailed(_Closed):
    document_id: Id
    run_id: Id
    reason: Literal["unreadable", "unsupported", "too_large", "internal_error"]
    unreadable_pages: Annotated[list[Page], Field(max_length=5000)]


class SessionRange(_Closed):
    """One page range of the session, in FILE pages. `first <= last` is not in the JSON Schema:
    core-api checks it before it enqueues, ai-service on receipt."""

    document_id: Id
    first: Page
    last: Page
    depth: Literal["deep", "skim", "unclear"]


class NoteFile(_Closed):
    object_key: ObjectKey
    mime: Literal["image/jpeg", "image/png", "application/pdf", "text/plain", "text/markdown"]


class SubmissionFile(_Closed):
    object_key: ObjectKey
    mime: Literal[
        "image/jpeg",
        "image/png",
        "application/pdf",
        "text/plain",
        "text/markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ]


class ExistingUnit(_Closed):
    unit_id: Id
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    summary: Annotated[str, StringConstraints(max_length=2000)]


class SessionConfirmed(_Closed):
    study_session_id: Id
    subject_id: Id
    ranges: Annotated[list[SessionRange], Field(max_length=6)]
    notes: Annotated[list[NoteFile], Field(max_length=20)]
    existing_units: Annotated[list[ExistingUnit], Field(max_length=500)]


class SubmissionCreated(_Closed):
    """The learner's words are in the file at `context_key`, never here (ADR-0013)."""

    submission_id: Id
    study_session_id: Id
    subject_id: Id
    file_keys: Annotated[list[SubmissionFile], Field(min_length=1, max_length=20)]
    context_key: ObjectKey


class SubmissionProcessed(_Closed):
    submission_id: Id
    study_session_id: Id
    run_id: Id
    result_key: ObjectKey


class SubmissionFailed(_Closed):
    submission_id: Id
    study_session_id: Id
    run_id: Id
    reason: Literal["unreadable", "llm_unavailable", "internal_error"]


class SessionProgress(_Closed):
    study_session_id: Id
    run_id: Id
    step: Literal["reading_notes", "splitting_units", "anchoring", "writing_questions"]
    percent: Annotated[int, Field(ge=0, le=100)]


class SessionProcessed(_Closed):
    study_session_id: Id
    run_id: Id
    result_key: ObjectKey


class SessionFailed(_Closed):
    study_session_id: Id
    run_id: Id
    reason: Literal["unreadable", "llm_unavailable", "internal_error"]


class GradeRequested(_Closed):
    attempt_id: Id
    request_key: ObjectKey


class GradeCompleted(_Closed):
    attempt_id: Id
    result_key: ObjectKey


class UnitSaved(_Closed):
    """A card was saved (US-02b AC9): ids and the revision only; the card is read by id."""

    unit_id: Id
    unit_rev: Annotated[int, Field(ge=1)]
    subject_id: Id


class UserDeleted(_Closed):
    pass


# --- Envelope -------------------------------------------------------------------------------


class _Envelope(_Closed):
    event_id: Id
    schema_version: Annotated[Literal[1], BeforeValidator(_not_bool)]
    occurred_at: Annotated[datetime, BeforeValidator(_utc_timestamp), AfterValidator(_is_utc)]
    user_id: Id
    trace_context: TraceContext


class DocumentUploadedEvent(_Envelope):
    event_type: Literal["document.uploaded.v1"]
    payload: DocumentUploaded


class DocumentIndexedEvent(_Envelope):
    event_type: Literal["document.indexed.v1"]
    payload: DocumentIndexed


class DocumentFailedEvent(_Envelope):
    event_type: Literal["document.failed.v1"]
    payload: DocumentFailed


class SessionConfirmedEvent(_Envelope):
    event_type: Literal["session.confirmed.v1"]
    payload: SessionConfirmed


class SessionProgressEvent(_Envelope):
    event_type: Literal["session.progress.v1"]
    payload: SessionProgress


class SessionProcessedEvent(_Envelope):
    event_type: Literal["session.processed.v1"]
    payload: SessionProcessed


class SessionFailedEvent(_Envelope):
    event_type: Literal["session.failed.v1"]
    payload: SessionFailed


class GradeRequestedEvent(_Envelope):
    event_type: Literal["grade.requested.v1"]
    payload: GradeRequested


class GradeCompletedEvent(_Envelope):
    event_type: Literal["grade.completed.v1"]
    payload: GradeCompleted


class SubmissionCreatedEvent(_Envelope):
    event_type: Literal["submission.created.v1"]
    payload: SubmissionCreated


class SubmissionProcessedEvent(_Envelope):
    event_type: Literal["submission.processed.v1"]
    payload: SubmissionProcessed


class SubmissionFailedEvent(_Envelope):
    event_type: Literal["submission.failed.v1"]
    payload: SubmissionFailed


class UnitSavedEvent(_Envelope):
    event_type: Literal["unit.saved.v1"]
    payload: UnitSaved


class UserDeletedEvent(_Envelope):
    event_type: Literal["user.deleted.v1"]
    payload: UserDeleted


Event = Annotated[
    DocumentUploadedEvent
    | DocumentIndexedEvent
    | DocumentFailedEvent
    | SessionConfirmedEvent
    | SessionProgressEvent
    | SessionProcessedEvent
    | SessionFailedEvent
    | GradeRequestedEvent
    | GradeCompletedEvent
    | UserDeletedEvent
    | SubmissionCreatedEvent
    | SubmissionProcessedEvent
    | SubmissionFailedEvent
    | UnitSavedEvent,
    Field(discriminator="event_type"),
]

_EVENT: TypeAdapter[Event] = TypeAdapter(Event)


def parse_event(raw: str | bytes) -> Event:
    """Validate one event as it travels (JSON text). Raises `pydantic.ValidationError`."""
    return _EVENT.validate_json(raw)


def dump_event(event: Event) -> str:
    """The event as it travels (JSON text). Producers write events only through this function:
    trace context fields that are absent are left out rather than written as null, which the
    contract refuses. Not `exclude_none`: the payload's required nullable fields (a session
    confirmed without a document) must stay, as null."""
    absent = {name for name, value in event.trace_context if value is None}
    return event.model_dump_json(exclude={"trace_context": absent})
