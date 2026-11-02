"""T9.11 (US-13 AC2): a DOCX or PPTX upload is indexed by its format: an outline and no page
files; a PDF is unchanged."""

import json
import uuid
from collections.abc import Iterator

import pytest
from redis import Redis

from ai_service.messaging.envelope import (
    DocumentFailedEvent,
    DocumentIndexedEvent,
    DocumentUploadedEvent,
    Event,
    parse_event,
)
from ai_service.tasks.index_document import IndexDocument, run_id_for
from tests.office.helpers import make_docx, make_pptx
from tests.tasks.helpers import FakeStorage, derived_prefix, upload


@pytest.fixture
def stream(redis_client: Redis) -> Iterator[str]:
    name = f"test.events.ai.{uuid.uuid4()}"
    yield name
    redis_client.delete(name)


def _upload(storage: FakeStorage, data: bytes, fmt: str) -> DocumentUploadedEvent:
    event = upload(storage, data, suffix="pdf")  # core keeps the raw key's .pdf suffix
    return event.model_copy(update={"payload": event.payload.model_copy(update={"format": fmt})})


def _sent(redis: Redis, stream: str) -> list[Event]:
    entries: list[tuple[str, dict[str, str]]] = redis.xrange(stream)  # pyright: ignore[reportAssignmentType]
    return [parse_event(fields["envelope"]) for _, fields in entries]


def test_us13_ac2_docx_headings_become_the_outline(redis_client: Redis, stream: str) -> None:
    storage = FakeStorage()
    docx = make_docx([(1, "Intro"), (None, "text " * 50), (1, "Methods"), (None, "more")])
    event = _upload(storage, docx, "docx")
    IndexDocument(storage=storage, redis=redis_client, stream=stream)(None, event)  # pyright: ignore[reportArgumentType]
    (out,) = _sent(redis_client, stream)
    assert isinstance(out, DocumentIndexedEvent)
    assert out.payload.format == "docx"
    assert out.payload.page_count == 2
    prefix = derived_prefix(event, run_id_for(event.event_id))
    outline = json.loads(storage.objects[f"{prefix}/outline.json"])
    assert outline["unit"] == "est_page"
    assert [(n["title"], n["source"]) for n in outline["nodes"]] == [
        ("Intro", "heading"),
        ("Methods", "heading"),
    ]
    assert not any(k.endswith(".png") for k in storage.objects)


def test_us13_ac2_pptx_without_sections_is_a_flat_temporary_outline(
    redis_client: Redis, stream: str
) -> None:
    storage = FakeStorage()
    event = _upload(storage, make_pptx([("A", "x"), ("B", "y"), ("C", "z")]), "pptx")
    IndexDocument(storage=storage, redis=redis_client, stream=stream)(None, event)  # pyright: ignore[reportArgumentType]
    (out,) = _sent(redis_client, stream)
    assert isinstance(out, DocumentIndexedEvent)
    assert (out.payload.format, out.payload.page_count) == ("pptx", 3)
    prefix = derived_prefix(event, run_id_for(event.event_id))
    outline = json.loads(storage.objects[f"{prefix}/outline.json"])
    assert outline["unit"] == "slide"
    assert {n["source"] for n in outline["nodes"]} == {"chunk10"}
    assert len(outline["nodes"]) == 3


def test_a_file_that_is_not_an_office_zip_fails_unreadable(
    redis_client: Redis, stream: str
) -> None:
    storage = FakeStorage()
    event = _upload(storage, b"not a zip at all", "docx")
    IndexDocument(storage=storage, redis=redis_client, stream=stream)(None, event)  # pyright: ignore[reportArgumentType]
    (out,) = _sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == "unreadable"


def test_a_pptx_declared_docx_fails_without_a_crash(redis_client: Redis, stream: str) -> None:
    storage = FakeStorage()
    event = _upload(storage, make_pptx([("A", "x")]), "docx")
    IndexDocument(storage=storage, redis=redis_client, stream=stream)(None, event)  # pyright: ignore[reportArgumentType]
    (out,) = _sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == "unreadable"
