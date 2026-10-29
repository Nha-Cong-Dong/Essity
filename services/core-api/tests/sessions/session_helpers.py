"""Builders for the session tests (T4.12): subjects, indexed documents, ai-service answers."""

import json
import uuid
from typing import Any

import httpx2
from sqlalchemy.orm import Session

from clock import FROZEN_NOW, future_exam
from core_api.db.models import Document, Subject, User
from core_api.repositories.subject import SubjectRepository
from fake_storage import FakeStorage

COMMON: dict[str, Any] = {
    "provider": "fake",
    "model": None,
    "prompt_version": "v1",
    "llm_call_id": None,
}


def subject_of(session: Session, user: User) -> Subject:
    subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam(60))
    session.flush()
    return subject


def indexed_document(
    session: Session,
    storage: FakeStorage,
    user: User,
    subject: Subject,
    *,
    name: str = "Chương 3",
    pages: int = 40,
    sha: str = "cd" * 32,
    toc: Any = None,
    labels: Any = None,
) -> Document:
    run = uuid.uuid4()
    prefix = f"users/{user.id}/subjects/{subject.id}/derived/{run}"
    document = Document(
        subject_id=subject.id,
        short_name=name,
        sha256=sha,
        size_bytes=100,
        object_key=f"users/{user.id}/subjects/{subject.id}/raw/{sha}.pdf",
        status="indexed",
        presigned_at=FROZEN_NOW,
        uploaded_at=FROZEN_NOW,
        run_id=run,
        page_count=pages,
        unreadable_pages=[],
        toc_key=f"{prefix}/toc.json",
        page_labels_key=f"{prefix}/page_labels.json",
        page_text_key=f"{prefix}/page_text.json",
        thumbnails_prefix=f"{prefix}/thumbs",
    )
    document.user_id = user.id
    session.add(document)
    session.flush()
    entries = toc if toc is not None else [{"title": "Chương 3", "level": 0, "page": 3}]
    storage.put(document.toc_key or "", json.dumps({"entries": entries}).encode(), None)
    labels = labels if labels is not None else [str(i - 1) for i in range(1, pages + 1)]
    storage.put(document.page_labels_key or "", json.dumps({"labels": labels}).encode(), None)
    return document


def proposed(document: Document, **over: Any) -> httpx2.Response:
    rng = {
        "document_id": str(document.id),
        "start_page": 3,
        "end_page": 9,
        "start_label": "2",
        "end_label": "8",
        "depth": "deep",
        "sections": ["Chương 3"],
        "basis_assumed_file": False,
    } | over.pop("range", {})
    body = (
        COMMON
        | {
            "status": "proposed",
            "run_id": str(uuid.uuid4()),
            "studied_on": "2026-10-22",
            "ranges": [rng],
        }
        | over
    )
    return httpx2.Response(200, json=body)
