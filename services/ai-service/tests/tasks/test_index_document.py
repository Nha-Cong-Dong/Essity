"""The `document.uploaded.v1` handler (T4.7): index a PDF, emit `document.indexed.v1` or
`document.failed.v1` on `events.ai`.

US-01 AC4: indexing makes no questions; the handler has no LLM and no question table, so the
only things it writes are derived files and one event.
"""

import io
import json
import logging
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from pypdf import PdfReader, PdfWriter
from redis import Redis
from sqlalchemy.orm import Session

from ai_service.messaging.consumer import Deferred
from ai_service.messaging.envelope import (
    DocumentFailedEvent,
    DocumentIndexedEvent,
    Event,
    parse_event,
)
from ai_service.pdf import PdfLimits
from ai_service.tasks.index_document import IndexDocument, indexed_event_id, run_id_for
from tests.pdf.helpers import Bookmark, Page, make_pdf
from tests.tasks.helpers import FakeStorage, derived_prefix, unavailable, upload

TEXT = "TCP three way handshake"


TOC_SCHEMA = Draft202012Validator(
    json.loads(
        (
            Path(__file__).resolve().parents[4] / "contracts" / "files" / "toc.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
)


@pytest.fixture
def stream(redis_client: Redis) -> Iterator[str]:
    name = f"test.events.ai.{uuid.uuid4()}"
    yield name
    redis_client.delete(name)


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def handler(redis_client: Redis, storage: FakeStorage, stream: str) -> IndexDocument:
    return IndexDocument(storage=storage, redis=redis_client, stream=stream)


def sent(redis: Redis, stream: str) -> list[Event]:
    entries: list[tuple[str, dict[str, str]]] = redis.xrange(stream)  # pyright: ignore[reportAssignmentType]
    return [parse_event(fields["envelope"]) for _, fields in entries]


def deck() -> bytes:
    return make_pdf(
        [Page(text=TEXT), Page(text="Chapter two " + TEXT), Page(image=True)],
        bookmarks=(Bookmark("Chapter 1", 0, (Bookmark("Section 1.1", 1),)),),
        labels=[(0, 0, "/r", "", 1), (1, 2, "/D", "", 1)],
    )


def test_t47_indexed_event_and_derived_files(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    event = upload(storage, deck())
    handler(session, event)

    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentIndexedEvent)
    run_id = run_id_for(event.event_id)
    prefix = derived_prefix(event, run_id)
    assert out.user_id == event.user_id
    assert out.event_id == indexed_event_id(event.event_id)
    assert out.trace_context == event.trace_context
    p = out.payload
    assert p.document_id == event.payload.document_id
    assert p.run_id == run_id
    assert p.page_count == 3
    assert p.toc_key == f"{prefix}/toc.json"
    assert p.page_labels_key == f"{prefix}/page_labels.json"
    assert p.page_text_key == f"{prefix}/page_text.json"
    assert p.thumbnails_prefix == f"{prefix}/thumbnails"
    # The scan has no text layer: it is read by vision (PLAN T4.7).
    assert p.unreadable_pages == [3]

    toc = json.loads(storage.objects[p.toc_key])
    assert [(e["title"], e["level"], e["page"]) for e in toc["entries"]] == [
        ("Chapter 1", 0, 1),
        ("Section 1.1", 1, 2),
    ]
    # contracts/files/toc.v1.schema.json: the writer's side (T4.9).
    assert cast(Any, TOC_SCHEMA).is_valid(toc)
    assert json.loads(storage.objects[p.page_labels_key])["labels"] == ["i", "1", "2"]
    pages = json.loads(storage.objects[p.page_text_key])["pages"]
    assert [x["page"] for x in pages] == [1, 2, 3]
    assert TEXT in pages[0]["text"]
    assert [x["needs_vision"] for x in pages] == [False, False, True]
    for n in (1, 2, 3):
        assert storage.objects[f"{prefix}/thumbnails/{n}.png"].startswith(b"\x89PNG")


def test_t47_no_toc_and_no_labels_are_empty_not_errors(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    handler(session, upload(storage, make_pdf([Page(text=TEXT)])))
    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentIndexedEvent)
    assert json.loads(storage.objects[out.payload.toc_key])["entries"] == []
    assert json.loads(storage.objects[out.payload.page_labels_key])["labels"] is None


def test_t47_same_event_twice_gives_same_run_and_keys(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    # The consumer may handle an event again after a crash: same run, same keys, same event id,
    # so core-api's own claim drops the second event.
    event = upload(storage, deck())
    handler(session, event)
    keys = set(storage.objects)
    handler(session, event)
    first, second = sent(redis_client, stream)
    assert first.event_id == second.event_id
    assert first.payload == second.payload
    assert set(storage.objects) == keys


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"", "unreadable"),
        (b"%PDF-1.4 not really", "unreadable"),
        (b"\x00" * 100, "unreadable"),
    ],
)
def test_t47_broken_file_is_failed_not_a_crash(
    handler: IndexDocument,
    storage: FakeStorage,
    redis_client: Redis,
    stream: str,
    session: Session,
    data: bytes,
    reason: str,
) -> None:
    handler(session, upload(storage, data))
    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == reason
    assert out.payload.unreadable_pages == []


def test_t47_too_many_pages_is_too_large(
    redis_client: Redis, storage: FakeStorage, stream: str, session: Session
) -> None:
    handler = IndexDocument(
        storage=storage, redis=redis_client, stream=stream, limits=PdfLimits(max_pages=2)
    )
    handler(session, upload(storage, deck()))
    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == "too_large"


def test_t47_file_over_byte_limit_is_too_large(
    redis_client: Redis, storage: FakeStorage, stream: str, session: Session
) -> None:
    handler = IndexDocument(
        storage=storage, redis=redis_client, stream=stream, limits=PdfLimits(max_bytes=100)
    )
    handler(session, upload(storage, deck()))
    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == "too_large"


def test_t47_encrypted_is_unsupported(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(deck())))
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    handler(session, upload(storage, buffer.getvalue()))
    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == "unsupported"


def test_t47_wrong_extension_is_unsupported(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    handler(session, upload(storage, deck(), suffix="png"))
    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == "unsupported"


def test_t47_content_not_matching_its_sha256_is_unreadable(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    # PLAN T4.5 risk: the storage may not verify the checksum, so the key's sha256 is checked.
    handler(session, upload(storage, deck(), name="b" * 64))
    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == "unreadable"


def test_t47_missing_object_is_failed(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    event = upload(storage, deck())
    storage.objects.clear()
    handler(session, event)
    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == "unreadable"


def test_t47_storage_down_on_read_is_deferred_and_sends_nothing(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    event = upload(storage, deck())
    storage.get_error = unavailable()
    with pytest.raises(Deferred):
        handler(session, event)
    assert sent(redis_client, stream) == []


def test_t47_storage_down_on_write_is_deferred_and_sends_nothing(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    event = upload(storage, deck())
    storage.put_error = unavailable()
    with pytest.raises(Deferred):
        handler(session, event)
    assert sent(redis_client, stream) == []


def test_t47_internal_error_in_worker_is_failed_without_the_message(
    redis_client: Redis,
    storage: FakeStorage,
    stream: str,
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(data: bytes, limits: PdfLimits) -> Any:
        raise RuntimeError(TEXT)

    handler = IndexDocument(storage=storage, redis=redis_client, stream=stream, analyze=broken)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError):
            handler(session, upload(storage, deck()))
    # A bug is a failure for the consumer to count towards the dead letter, not a verdict on the
    # file; nothing was sent, and the document's text is nowhere in the log.
    assert sent(redis_client, stream) == []
    assert TEXT not in caplog.text


def test_t47_nothing_in_the_log_names_the_document(
    handler: IndexDocument,
    storage: FakeStorage,
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    event = upload(storage, deck())
    with caplog.at_level(logging.DEBUG):
        handler(session, event)
    assert TEXT not in caplog.text
    assert event.payload.object_key not in caplog.text


def test_t47_registered_for_document_uploaded() -> None:
    from ai_service.handlers import build_handlers

    handlers = build_handlers(redis=None, storage=FakeStorage())  # pyright: ignore[reportArgumentType]
    assert "document.uploaded.v1" in handlers


def test_t47_key_of_another_user_is_failed_without_reading_storage(
    handler: IndexDocument, storage: FakeStorage, redis_client: Redis, stream: str, session: Session
) -> None:
    event = upload(storage, deck())
    other = event.model_copy(update={"user_id": uuid.uuid4()})
    storage.get_error = AssertionError("storage must not be read")
    handler(session, other)
    (out,) = sent(redis_client, stream)
    assert isinstance(out, DocumentFailedEvent)
    assert out.payload.reason == "unsupported"
    assert storage.puts == []
