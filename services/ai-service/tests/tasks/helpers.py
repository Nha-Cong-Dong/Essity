"""An in-memory storage and uploaded events for the document indexer's tests (T4.7)."""

import hashlib
import json
import uuid
from typing import Any

from ai_service.clients.storage import ObjectNotFound, ObjectTooLarge, StorageUnavailable
from ai_service.messaging.envelope import DocumentUploadedEvent, parse_event
from tests.messaging.helpers import uploaded


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.get_error: Exception | None = None
        self.put_error: Exception | None = None
        self.puts: list[str] = []

    def get(self, key: str, *, max_bytes: int) -> bytes:
        if self.get_error is not None:
            raise self.get_error
        if key not in self.objects:
            raise ObjectNotFound
        if len(self.objects[key]) > max_bytes:
            raise ObjectTooLarge
        return self.objects[key]

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        if self.put_error is not None:
            raise self.put_error
        self.objects[key] = data
        self.puts.append(key)


def unavailable() -> Exception:
    return StorageUnavailable()


def upload(
    storage: FakeStorage, pdf: bytes, *, name: str | None = None, suffix: str = "pdf"
) -> DocumentUploadedEvent:
    """Put `pdf` in the storage under a key whose name is its sha256, and return the event."""
    raw: dict[str, Any] = uploaded()
    sha = name or hashlib.sha256(pdf).hexdigest()
    key = raw["payload"]["object_key"].rsplit("/", 1)[0] + f"/{sha}.{suffix}"
    raw["payload"]["object_key"] = key
    storage.objects[key] = pdf
    event = parse_event(json.dumps(raw))
    assert isinstance(event, DocumentUploadedEvent)
    return event


def derived_prefix(event: DocumentUploadedEvent, run_id: uuid.UUID) -> str:
    key = event.payload.object_key
    return key.split("/raw/")[0] + f"/derived/{run_id}"
