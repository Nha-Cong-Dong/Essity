"""The `session.confirmed.v1` handler (T4.16b, US-02 AC7/8/12/13, US-02b, US-04b): page text and
notes in, units and questions in a result file, `session.processed.v1` out. Fake model on the
real test database; storage and Redis as in T4.7 and T4.19."""

import json
import logging
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from redis import Redis
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.clients.storage import StorageUnavailable
from ai_service.db.models import LlmCall, PipelineRun
from ai_service.llm.client import LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.types import ProviderError
from ai_service.messaging.consumer import Deferred
from ai_service.messaging.envelope import (
    SessionConfirmedEvent,
    SessionFailedEvent,
    SessionProcessedEvent,
    SessionProgressEvent,
    parse_event,
)
from ai_service.tasks.process_session import (
    ProcessSession,
    fake_chunk,
    fake_questions,
    result_key_for,
)
from tests.llm.helpers import NoQuota
from tests.tasks.helpers import FakeStorage

_SCHEMA_FILE = (
    Path(__file__).resolve().parents[4] / "contracts" / "files" / "session-result.v1.schema.json"
)
SCHEMA: Any = Draft202012Validator(json.loads(_SCHEMA_FILE.read_text(encoding="utf-8")))
USER = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SUBJECT = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
DOC = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
PAGE_TEXTS = {
    1: "Mitochondria are the site of cellular respiration in eukaryotic cells.",
    2: "The Krebs cycle oxidises acetyl-CoA to carbon dioxide in the matrix.",
    3: "Ribosomes translate messenger RNA into protein chains.",
}
NOTE = "ghi chu: ty the la noi hop ho hap te bao."
SECRET = "SECRET-NOTE-TEXT-9921"


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_audit(sessions: sessionmaker[Session]) -> None:
    with sessions.begin() as s:
        s.execute(delete(LlmCall).where(LlmCall.user_id == USER))
        s.execute(delete(PipelineRun).where(PipelineRun.user_id == USER))


@pytest.fixture
def stream(redis_client: Redis) -> Iterator[str]:
    name = f"test.events.ai.{uuid.uuid4()}"
    yield name
    redis_client.delete(name)


def prefix() -> str:
    return f"users/{USER}/subjects/{SUBJECT}"


def index(storage: FakeStorage, pages: dict[int, str] | None = None) -> None:
    pages = PAGE_TEXTS if pages is None else pages
    text_key = f"{prefix()}/documents/{DOC}/derived/run1/page_text.json"
    storage.objects[text_key] = json.dumps(
        {"pages": [{"page": n, "text": t, "needs_vision": False} for n, t in pages.items()]}
    ).encode()
    storage.objects[f"{prefix()}/documents/{DOC}/index.json"] = json.dumps(
        {"page_text_key": text_key, "page_count": len(pages)}
    ).encode()


def confirmed(
    ranges: list[tuple[uuid.UUID, int, int]] | None = None,
    notes: list[dict[str, str]] | None = None,
    existing: list[dict[str, Any]] | None = None,
) -> SessionConfirmedEvent:
    ranges = [(DOC, 1, 2)] if ranges is None else ranges
    event = parse_event(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "session.confirmed.v1",
                "schema_version": 1,
                "occurred_at": "2026-10-29T08:30:00.000000Z",
                "user_id": str(USER),
                "trace_context": {},
                "payload": {
                    "study_session_id": str(uuid.uuid4()),
                    "subject_id": str(SUBJECT),
                    "ranges": [
                        {"document_id": str(d), "first": a, "last": b, "depth": "deep"}
                        for d, a, b in ranges
                    ],
                    "notes": notes or [],
                    "existing_units": existing or [],
                },
            }
        )
    )
    assert isinstance(event, SessionConfirmedEvent)
    return event


def note(storage: FakeStorage, text: str = NOTE, mime: str = "text/plain") -> dict[str, str]:
    key = f"{prefix()}/notes/{uuid.uuid4()}.txt"
    storage.objects[key] = text.encode()
    return {"object_key": key, "mime": mime}


class Down:
    """A model that never answers."""

    provider = "anthropic"
    fixed_model: str | None = None
    params: dict[str, Any] = {}

    def complete(self, request: object, *, model: str, timeout: float) -> object:
        raise ProviderError("timeout")


def broken_chunker() -> FakeAdapter:
    return FakeAdapter({"chunk_units": lambda r: "not json", "generate_questions": fake_questions})


def handler(
    storage: FakeStorage,
    redis: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    adapter: Any = None,
    *,
    disabled: bool = False,
) -> ProcessSession:
    llm = (
        None
        if disabled
        else LlmClient(
            adapter
            or FakeAdapter({"chunk_units": fake_chunk, "generate_questions": fake_questions}),
            sessions,
            models={"chunk_units": "claude-haiku-5-5", "generate_questions": "claude-haiku-5-5"},
            quota_guard=NoQuota(),
        )
    )
    return ProcessSession(storage=storage, redis=redis, llm=llm, sessions=sessions, stream=stream)


def sent(redis: Redis, stream: str) -> list[Any]:
    return [parse_event(f["envelope"]) for _, f in cast(Any, redis.xrange(stream))]


def result(storage: FakeStorage, event: SessionConfirmedEvent) -> dict[str, Any]:
    body = json.loads(storage.objects[result_key_for(event)])
    assert list(SCHEMA.iter_errors(body)) == []
    return body


def run(h: ProcessSession, event: SessionConfirmedEvent) -> None:
    h(cast(Session, None), event)


def test_t416b_chain_writes_units_questions_and_announces(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed(notes=[note(storage)])
    run(handler(storage, redis_client, stream, sessions), event)

    body = result(storage, event)
    assert body["study_session_id"] == str(event.payload.study_session_id)
    # one unit per source: two pages and the notes
    assert len(body["units"]) == 3
    assert {a["page_no"] for u in body["units"] for a in u["anchors"]} == {1, 2, None}
    assert {q["unit_id"] for q in body["questions"]} == {u["unit_id"] for u in body["units"]}
    out = sent(redis_client, stream)
    progress = [e.payload for e in out if isinstance(e, SessionProgressEvent)]
    assert progress[0].step == "reading_notes"
    assert "splitting_units" in {p.step for p in progress}
    assert progress[-1].step == "writing_questions"
    percents = [p.percent for p in progress]
    assert percents == sorted(percents)
    last = out[-1]
    assert isinstance(last, SessionProcessedEvent)
    assert last.payload.result_key == result_key_for(event)
    assert last.payload.study_session_id == event.payload.study_session_id


def test_t416b_anchors_are_cut_from_the_page_text(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    run(handler(storage, redis_client, stream, sessions), event)
    for unit in result(storage, event)["units"]:
        for a in unit["anchors"]:
            assert PAGE_TEXTS[a["page_no"]][a["start"] : a["end"]] == a["quote_text"]


def test_t416b_only_the_pages_of_the_range_are_read(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed(ranges=[(DOC, 2, 3)])
    run(handler(storage, redis_client, stream, sessions), event)
    pages = {a["page_no"] for u in result(storage, event)["units"] for a in u["anchors"]}
    assert pages == {2, 3}


def test_t416b_same_event_twice_pays_once_and_announces_the_same_event(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed()
    h = handler(storage, redis_client, stream, sessions)
    run(h, event)
    with sessions() as s:
        calls = len(s.scalars(select(LlmCall).where(LlmCall.user_id == USER)).all())
    first = storage.objects[result_key_for(event)]
    run(h, event)
    assert storage.objects[result_key_for(event)] == first
    with sessions() as s:
        assert len(s.scalars(select(LlmCall).where(LlmCall.user_id == USER)).all()) == calls
    processed = [e for e in sent(redis_client, stream) if isinstance(e, SessionProcessedEvent)]
    assert len(processed) == 2
    assert processed[0].event_id == processed[1].event_id


def test_t416b_inverted_range_is_failed_before_anything_is_read(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    run(handler(storage, redis_client, stream, sessions), confirmed(ranges=[(DOC, 3, 1)]))
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SessionFailedEvent)
    assert out.payload.reason == "internal_error"
    assert storage.puts == []


def test_t416b_image_and_pdf_notes_are_skipped_with_a_reason(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    notes = [note(storage, mime="image/png"), note(storage, mime="application/pdf")]
    event = confirmed(notes=notes)
    run(handler(storage, redis_client, stream, sessions), event)
    skipped = result(storage, event)["skipped"]
    assert [s for s in skipped if s["kind"] == "note"] == [
        {"kind": "note", "ref": 1, "reason": "needs_ocr"},
        {"kind": "note", "ref": 2, "reason": "needs_ocr"},
    ]
    assert isinstance(sent(redis_client, stream)[-1], SessionProcessedEvent)


def test_t416b_notes_only_session_works(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = confirmed(ranges=[], notes=[note(storage)])
    run(handler(storage, redis_client, stream, sessions), event)
    body = result(storage, event)
    assert [a["source"] for u in body["units"] for a in u["anchors"]] == ["notes"]


def test_t416b_nothing_readable_is_unreadable(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()  # no index for the document, only an image note
    event = confirmed(notes=[note(storage, mime="image/jpeg")])
    run(handler(storage, redis_client, stream, sessions), event)
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SessionFailedEvent)
    assert out.payload.reason == "unreadable"
    assert result_key_for(event) not in storage.objects


def test_t416b_pointer_to_a_key_of_another_user_is_not_followed(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    other = f"users/{uuid.uuid4()}/subjects/{SUBJECT}/documents/{DOC}/derived/r/page_text.json"
    storage.objects[other] = json.dumps({"pages": [{"page": 1, "text": SECRET}]}).encode()
    storage.objects[f"{prefix()}/documents/{DOC}/index.json"] = json.dumps(
        {"page_text_key": other, "page_count": 1}
    ).encode()
    event = confirmed(ranges=[(DOC, 1, 1)])
    run(handler(storage, redis_client, stream, sessions), event)
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SessionFailedEvent) and out.payload.reason == "unreadable"


def test_t416b_model_down_is_failed_llm_unavailable(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    run(handler(storage, redis_client, stream, sessions, Down()), confirmed())
    out = sent(redis_client, stream)
    assert isinstance(out[-1], SessionFailedEvent)
    assert out[-1].payload.reason == "llm_unavailable"
    assert not any(isinstance(e, SessionProcessedEvent) for e in out)
    assert storage.puts == []


def test_t416b_disabled_model_is_failed_llm_unavailable(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    run(handler(storage, redis_client, stream, sessions, disabled=True), confirmed())
    (out,) = sent(redis_client, stream)
    assert isinstance(out, SessionFailedEvent) and out.payload.reason == "llm_unavailable"


def test_t416b_model_that_always_breaks_the_rules_is_failed_internal_error(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    run(handler(storage, redis_client, stream, sessions, broken_chunker()), confirmed())
    out = sent(redis_client, stream)
    assert isinstance(out[-1], SessionFailedEvent)
    assert out[-1].payload.reason == "internal_error"
    with sessions() as s:
        runs = s.scalars(select(PipelineRun).where(PipelineRun.user_id == USER)).all()
    assert [r.status for r in runs if r.task == "chunk_units"] == ["failed"]


def test_t416b_a_crash_inside_the_model_call_is_failed_not_raised(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    def boom(request: object) -> str:
        raise RuntimeError(SECRET)

    storage = FakeStorage()
    index(storage)
    adapter = FakeAdapter({"chunk_units": boom, "generate_questions": fake_questions})  # pyright: ignore[reportArgumentType]
    run(handler(storage, redis_client, stream, sessions, adapter), confirmed())
    out = sent(redis_client, stream)
    assert isinstance(out[-1], SessionFailedEvent) and out[-1].payload.reason == "internal_error"


def test_t416b_storage_down_is_deferred(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    storage.get_error = StorageUnavailable()
    with pytest.raises(Deferred):
        run(handler(storage, redis_client, stream, sessions), confirmed())
    assert sent(redis_client, stream) == []


def test_t416b_storage_down_on_write_is_deferred(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    storage.put_error = StorageUnavailable()
    with pytest.raises(Deferred):
        run(handler(storage, redis_client, stream, sessions), confirmed())
    assert not any(isinstance(e, SessionProcessedEvent) for e in sent(redis_client, stream))


def test_t416b_many_pages_are_split_into_batches(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    pages = {n: f"Page number {n} says something distinct about topic {n}." for n in range(1, 46)}
    index(storage, pages)
    event = confirmed(ranges=[(DOC, 1, 45)])
    run(handler(storage, redis_client, stream, sessions), event)
    body = result(storage, event)
    assert len(body["units"]) == 45
    with sessions() as s:
        runs = s.scalars(select(PipelineRun).where(PipelineRun.user_id == USER)).all()
    assert {r.task for r in runs} == {"chunk_units", "generate_questions"}
    assert all(r.status == "succeeded" for r in runs)
    splitting = [
        e.payload.percent
        for e in sent(redis_client, stream)
        if isinstance(e, SessionProgressEvent) and e.payload.step == "splitting_units"
    ]
    assert len(splitting) == 3  # 45 pages, 20 a batch


def test_t416b_an_existing_unit_gets_anchors_and_no_question(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    index(storage)
    existing_id = str(uuid.uuid4())
    # the title the fake model gives page 1: the code merges instead of creating
    event = confirmed(
        ranges=[(DOC, 1, 1)],
        existing=[{"unit_id": existing_id, "title": "Ý chính D1.p1", "summary": "x"}],
    )
    run(handler(storage, redis_client, stream, sessions), event)
    body = result(storage, event)
    assert body["units"] == []
    assert [m["existing_unit_id"] for m in body["merges"]] == [existing_id]
    assert body["questions"] == []


def test_t416b_nothing_in_the_log_names_the_text(
    redis_client: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = FakeStorage()
    index(storage)
    event = confirmed(notes=[note(storage, SECRET)])
    with caplog.at_level(logging.DEBUG):
        run(handler(storage, redis_client, stream, sessions, broken_chunker()), event)
    assert SECRET not in caplog.text
    assert "Mitochondria" not in caplog.text


def test_t416b_the_handler_is_registered() -> None:
    from ai_service.handlers import build_handlers

    handlers = build_handlers(redis=None, storage=None, llm=None, sessions=None)  # pyright: ignore[reportArgumentType]
    assert isinstance(handlers["session.confirmed.v1"], ProcessSession)
