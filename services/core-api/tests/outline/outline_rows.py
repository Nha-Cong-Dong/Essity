"""Rows for the outline tests (T7.4): a subject with a textbook and its stored outline."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from clock import FROZEN_NOW, future_exam
from core_api.db.models import DocSection, Document, Subject, User
from core_api.repositories.doc_section import DocSectionRepository, NewSection
from core_api.repositories.subject import SubjectRepository

PAGES = 40


def subject_of(session: Session, user: User, name: str = "Mạng") -> Subject:
    subject, _ = SubjectRepository(session, user.id).create_with_exam(name, future_exam(60))
    session.flush()
    return subject


def document_in(
    session: Session,
    user: User,
    subject: Subject,
    name: str = "Giáo trình",
    *,
    role: str = "textbook",
    status: str = "indexed",
    pages: int | None = PAGES,
) -> Document:
    sha = uuid.uuid4().hex + uuid.uuid4().hex
    run = uuid.uuid4()
    base = f"users/{user.id}/subjects/{subject.id}"
    extra: dict[str, Any] = {}
    if status == "indexed":
        extra = {
            "run_id": run,
            "page_count": pages,
            "toc_key": f"{base}/derived/{run}/toc.json",
            "page_labels_key": f"{base}/derived/{run}/page_labels.json",
            "page_text_key": f"{base}/derived/{run}/page_text.json",
            "thumbnails_prefix": f"{base}/derived/{run}/thumbs",
        }
    if status == "failed":
        extra = {"failure_reason": "unreadable"}
    document = Document(
        subject_id=subject.id,
        short_name=name,
        sha256=sha,
        size_bytes=100,
        object_key=f"{base}/raw/{sha}.pdf",
        status=status,
        role=role,
        presigned_at=FROZEN_NOW,
        uploaded_at=None if status in ("pending", "rejected") else FROZEN_NOW,
        **extra,
    )
    document.user_id = user.id
    session.add(document)
    session.flush()
    return document


# Chapter 1 (1-20) with sections 1.1 (1-8) and 1.2 (9-20); chapter 2 (21-40).
TREE = [
    NewSection("Chương 1", None, 1, 20, 20, "page", "bookmark"),
    NewSection("1.1", 0, 1, 8, 8, "page", "bookmark"),
    NewSection("1.2", 0, 9, 20, 12, "page", "bookmark"),
    NewSection("Chương 2", None, 21, 40, 20, "page", "bookmark"),
]


def with_outline(
    session: Session, user: User, document: Document, nodes: list[NewSection] | None = None
) -> dict[str, DocSection]:
    rows = DocSectionRepository(session, user.id).replace(
        document.id, document.subject_id, nodes or TREE
    )
    return {row.title: row for row in rows}
