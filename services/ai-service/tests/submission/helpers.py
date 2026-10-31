"""Builders for the `submission.created.v1` handler's tests (T7.7): a storage with a context and
files, a counting fake model, and the handler on the real test database and Redis."""

import io
import json
import uuid
from collections.abc import Callable
from typing import Any, cast

from PIL import Image
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ai_service.llm.client import LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.types import LlmRequest
from ai_service.messaging.envelope import SubmissionCreatedEvent, parse_event
from ai_service.tasks.process_session import fake_chunk
from ai_service.tasks.process_submission import ProcessSubmission, fake_read_notes
from tests.llm.helpers import NoQuota
from tests.tasks.helpers import FakeStorage

USER = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SUBJECT = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
DOC = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
SEC1 = uuid.UUID("11111111-1111-4111-8111-111111111111")
SEC2 = uuid.UUID("22222222-2222-4222-8222-222222222222")
PAGES = {
    1: "Mitochondria are the site of cellular respiration in eukaryotic cells.",
    2: "The Krebs cycle oxidises acetyl-CoA to carbon dioxide in the matrix.",
    3: "Ribosomes translate messenger RNA into protein chains.",
}
MODELS = {"draft_units": "claude-haiku-5-5", "read_notes": "claude-haiku-5-5"}


def prefix() -> str:
    return f"users/{USER}/subjects/{SUBJECT}"


def index(storage: FakeStorage, pages: dict[int, str] | None = None) -> None:
    pages = PAGES if pages is None else pages
    text_key = f"{prefix()}/documents/{DOC}/derived/run1/page_text.json"
    storage.objects[text_key] = json.dumps(
        {"pages": [{"page": n, "text": t, "needs_vision": False} for n, t in pages.items()]}
    ).encode()
    storage.objects[f"{prefix()}/documents/{DOC}/index.json"] = json.dumps(
        {"page_text_key": text_key, "page_count": len(pages)}
    ).encode()


def mention(
    first: int | None, last: int | None, section: uuid.UUID | None = SEC1
) -> dict[str, Any]:
    return {
        "document_id": str(DOC),
        "section_id": str(section) if section else None,
        "first_page": first,
        "last_page": last,
    }


def file_of(storage: FakeStorage, data: bytes, mime: str) -> dict[str, str]:
    key = f"users/{USER}/sessions/{uuid.uuid4()}/notes/{uuid.uuid4().hex}.bin"
    storage.objects[key] = data
    return {"object_key": key, "mime": mime}


def submitted(
    storage: FakeStorage,
    *,
    files: list[dict[str, str]] | None = None,
    mentions: list[dict[str, Any]] | None = None,
    description: str | None = None,
    submission_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    write_context: bool = True,
) -> SubmissionCreatedEvent:
    submission_id = submission_id or uuid.uuid4()
    session_id = session_id or uuid.uuid4()
    context_key = f"users/{USER}/sessions/{session_id}/context/{submission_id}.json"
    if write_context:
        storage.objects[context_key] = json.dumps(
            {
                "version": 1,
                "description": description,
                "mentions": [mention(1, 2)] if mentions is None else mentions,
                "existing_units": [],
            }
        ).encode()
    event = parse_event(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "submission.created.v1",
                "schema_version": 1,
                "occurred_at": "2026-11-01T08:30:00.000000Z",
                "user_id": str(USER),
                "trace_context": {},
                "payload": {
                    "submission_id": str(submission_id),
                    "study_session_id": str(session_id),
                    "subject_id": str(SUBJECT),
                    "file_keys": files or [file_of(storage, b"x", "text/plain")],
                    "context_key": context_key,
                },
            }
        )
    )
    assert isinstance(event, SubmissionCreatedEvent)
    return event


def again(event: SubmissionCreatedEvent) -> SubmissionCreatedEvent:
    """The same submission delivered as a new event (core retrying after `llm_unavailable`)."""
    return event.model_copy(update={"event_id": uuid.uuid4()})


def png(n: int = 0, size: int = 80) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (size, size), (n % 256, n // 256, 9)).save(out, format="PNG")
    return out.getvalue()


def scanned_pdf(pages: int) -> bytes:
    """A PDF whose pages are pictures only: no text layer, so each is read by vision."""
    images = [
        Image.new("RGB", (120, 120), (i * 9 % 256, 255 - i * 7, i * 5 % 256)) for i in range(pages)
    ]
    out = io.BytesIO()
    images[0].save(out, format="PDF", save_all=True, append_images=images[1:])
    return out.getvalue()


class Model:
    """Counts the calls of each task and keeps every request."""

    def __init__(
        self,
        draft: Callable[[LlmRequest], str] = fake_chunk,
        read: Callable[[LlmRequest], str] = fake_read_notes,
    ) -> None:
        self.requests: list[LlmRequest] = []
        self._draft, self._read = draft, read

    def _record(self, fn: Callable[[LlmRequest], str]) -> Callable[[LlmRequest], str]:
        def run(request: LlmRequest) -> str:
            self.requests.append(request)
            return fn(request)

        return run

    @property
    def adapter(self) -> FakeAdapter:
        return FakeAdapter(
            {"draft_units": self._record(self._draft), "read_notes": self._record(self._read)}
        )

    def calls(self, task: str) -> list[LlmRequest]:
        return [r for r in self.requests if r.task == task]


def handler(
    storage: FakeStorage,
    redis: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    model: Model | None = None,
    *,
    quota: Any = None,
) -> ProcessSubmission:
    llm = LlmClient(
        (model or Model()).adapter,
        sessions,
        models=MODELS,
        quota_guard=quota or NoQuota(),
    )
    return ProcessSubmission(
        storage=storage, redis=redis, llm=llm, sessions=sessions, stream=stream
    )


def run(h: ProcessSubmission, event: SubmissionCreatedEvent) -> None:
    h(cast(Session, None), event)
