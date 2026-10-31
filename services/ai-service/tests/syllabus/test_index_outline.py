"""T7.4 (US-13 AC2, AC3, AC9): indexing writes `outline.json`; the model is asked only for a
contents page, and a book with bookmarks costs no call."""

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from redis import Redis
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.db.models import LlmCall, PipelineRun
from ai_service.llm.client import LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.types import LlmRequest
from ai_service.messaging.envelope import DocumentIndexedEvent
from ai_service.tasks.index_document import IndexDocument, run_id_for
from ai_service.tasks.syllabus import fake_toc, outline_file
from tests.llm.helpers import NoQuota
from tests.pdf.helpers import Bookmark, Page, make_pdf
from tests.tasks.helpers import FakeStorage, derived_prefix, upload

MODEL = "claude-haiku-5-5"
TOC_REPLY = json.dumps(
    {
        "entries": [
            {"title": "Intro", "level": 0, "page": 1},
            {"title": "Methods", "level": 0, "page": 5},
        ]
    }
)


class Responder:
    def __init__(self, reply: str = TOC_REPLY) -> None:
        self.reply = reply
        self.requests: list[LlmRequest] = []

    def __call__(self, request: LlmRequest) -> str:
        self.requests.append(request)
        return self.reply


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def stream(redis_client: Redis) -> Iterator[str]:
    name = f"test.events.ai.{uuid.uuid4()}"
    yield name
    redis_client.delete(name)


def _handler(
    redis: Redis,
    storage: FakeStorage,
    stream: str,
    sessions: sessionmaker[Session],
    responder: Responder | None,
) -> IndexDocument:
    llm = (
        None
        if responder is None
        else LlmClient(
            FakeAdapter({"syllabus_toc": responder}),
            sessions,
            models={"syllabus_toc": MODEL},
            quota_guard=NoQuota(),
        )
    )
    return IndexDocument(storage=storage, redis=redis, stream=stream, llm=llm, sessions=sessions)


def _outline(storage: FakeStorage, event: Any) -> dict[str, Any]:
    prefix = derived_prefix(event, run_id_for(event.event_id))
    return json.loads(storage.objects[f"{prefix}/outline.json"])


def _toc_book() -> bytes:
    pages = [Page(text="Table of contents\nIntro .... 1\nMethods .... 5")]
    pages += [Page(text="Introduction\ntext")] + [Page(text=f"Body {i}") for i in range(2, 9)]
    pages[5] = Page(text="Methods\ntext")
    return make_pdf(pages)


def _calls(engine: Engine) -> int:
    with Session(engine) as session:
        return len(list(session.scalars(select(LlmCall))))


def test_us13_ac3_bookmarked_pdf_costs_no_call(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session], engine: Engine
) -> None:
    storage, responder = FakeStorage(), Responder()
    pdf = make_pdf(
        [Page(text="a"), Page(text="b"), Page(text="c")],
        bookmarks=(Bookmark("Chapter 1", 0, (Bookmark("Section 1.1", 1),)), Bookmark("Two", 2)),
    )
    event = upload(storage, pdf)
    before = _calls(engine)
    _handler(redis_client, storage, stream, sessions, responder)(Session(), event)
    assert responder.requests == []
    assert _calls(engine) == before
    outline = _outline(storage, event)
    assert {n["source"] for n in outline["nodes"]} == {"bookmark"}
    assert [n["title"] for n in outline["nodes"]] == [
        "Chapter 1",
        "Chapter 1",
        "Section 1.1",
        "Two",
    ]
    assert [n["parent"] for n in outline["nodes"]] == [None, 0, 0, None]


def test_us13_ac2_contents_page_is_one_call_and_audited(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session], engine: Engine
) -> None:
    storage, responder = FakeStorage(), Responder()
    event = upload(storage, _toc_book())
    _handler(redis_client, storage, stream, sessions, responder)(Session(), event)
    assert len(responder.requests) == 1
    request = responder.requests[0]
    assert request.task == "syllabus_toc"
    assert request.user_id == event.user_id and request.subject_id == event.payload.subject_id
    outline = _outline(storage, event)
    assert {n["source"] for n in outline["nodes"]} == {"llm_toc"}
    assert outline["unit"] == "page"
    with Session(engine) as session:
        run = session.scalars(
            select(PipelineRun).where(PipelineRun.id == request.pipeline_run_id)
        ).one()
    assert (run.task, run.status, run.error_code) == ("syllabus_toc", "succeeded", None)


def test_us13_ac9_no_model_falls_back_to_chunk10(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session], engine: Engine
) -> None:
    storage = FakeStorage()
    event = upload(storage, _toc_book())
    before = _calls(engine)
    _handler(redis_client, storage, stream, sessions, None)(Session(), event)
    assert _calls(engine) == before
    nodes = _outline(storage, event)["nodes"]
    assert {n["source"] for n in nodes} == {"chunk10"}
    assert (nodes[0]["page_start"], nodes[-1]["page_end"]) == (1, 9)


def test_us13_ac9_text_free_scan_is_chunk10_without_a_call(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage, responder = FakeStorage(), Responder()
    event = upload(storage, make_pdf([Page(image=True), Page(image=True)]))
    _handler(redis_client, storage, stream, sessions, responder)(Session(), event)
    assert responder.requests == []
    assert [n["source"] for n in _outline(storage, event)["nodes"]] == ["chunk10"]


def test_the_outline_file_is_written_with_the_other_derived_files_and_event_is_unchanged(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = upload(storage, _toc_book())
    _handler(redis_client, storage, stream, sessions, Responder())(Session(), event)
    ((_, fields),) = redis_client.xrange(stream)  # type: ignore[misc]
    from ai_service.messaging.envelope import parse_event

    out = parse_event(fields["envelope"])  # pyright: ignore[reportOptionalSubscript, reportUnknownArgumentType]
    assert isinstance(out, DocumentIndexedEvent)
    prefix = out.payload.toc_key.rsplit("/", 1)[0]
    assert f"{prefix}/outline.json" in storage.objects


def test_outline_file_parents_follow_levels() -> None:
    from ai_service.tasks.syllabus import SyllabusNode

    def node(title: str, level: int, order: int) -> SyllabusNode:
        return SyllabusNode(title, level, order, order + 1, order + 1, 1, source="bookmarks")

    nodes = [
        node("A", 0, 0),
        node("A1", 1, 1),
        node("A1a", 2, 2),
        node("A2", 1, 3),
        node("B", 0, 4),
    ]
    assert [n["parent"] for n in outline_file(nodes)["nodes"]] == [None, 0, 1, 0, None]


def test_fake_provider_answer_is_empty_entries() -> None:
    assert json.loads(fake_toc(None)) == {"entries": []}  # type: ignore[arg-type]
