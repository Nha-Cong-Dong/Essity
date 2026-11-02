"""What the command bar tells the parser (T9.2e, ADR-0030, US-18 AC7): ids and titles, never the
text of a document or a card. Cards and sections go in the order the screen shows them (T9.1 Y1:
the model reads "the second card" by position): sections in outline order document by document,
cards by the section that holds them (outline order, then oldest first), the ones in no section
last. Each list is cut at the parser's limits; a title is cut to the parser's length."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from core_api.repositories.doc_section import DocSectionRepository
from core_api.repositories.document import DocumentRepository
from core_api.repositories.practice_types import PracticeTypeRepository
from core_api.repositories.question import QuestionRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import DraftRepository

# ai-service's limits (`commands.schema`): at most 200 items a list, 50 documents, 120 characters
# a title, 60 000 characters of titles in all.
MAX_ITEMS = 200
MAX_DOCUMENTS = 50
MAX_TITLE = 120
MAX_TOTAL = 60_000


def _title(text: str, fallback: str) -> str:
    cleaned = " ".join(text.replace("\x00", " ").split())[:MAX_TITLE].strip()
    return cleaned or fallback


def build_parse_payload(
    session: Session, user_id: uuid.UUID, subject_id: uuid.UUID, command: str, today: date
) -> dict[str, Any]:
    """The request body for ai-service. The subject must be this user's (the caller checks)."""
    drafts = DraftRepository(session, user_id)
    _, units, links = drafts.by_section(subject_id)
    sections = _outline(session, user_id, subject_id)
    rank = {s["id"]: i for i, s in enumerate(sections)}
    first: dict[uuid.UUID, int] = {}
    for unit_id, section_id in links:
        if section_id in rank:
            first[unit_id] = min(first.get(unit_id, len(rank)), rank[section_id])
    # Python's sort is stable: within one section the oldest card stays first.
    ordered = sorted(units, key=lambda u: first.get(u.id, len(rank) + 1))
    cards = [{"id": u.id, "title": _title(u.title, "Thẻ")} for u in ordered]
    subjects = [
        {"id": s.id, "title": _title(s.name, "Môn học")}
        for s in SubjectRepository(session, user_id).list()
    ]
    types = [
        {"id": t.id, "title": _title(t.name, "Dạng câu")}
        for t in PracticeTypeRepository(session, user_id).of_subject(subject_id)
    ]
    questions = [
        {"id": q.id, "title": _title(q.prompt, "Câu hỏi")}
        for q in QuestionRepository(session, user_id).active_of_subject(subject_id, MAX_ITEMS)
    ]
    documents = [
        {"id": d.id, "title": _title(d.short_name, "Tài liệu")}
        for d in DocumentRepository(session, user_id).of_subject(subject_id)
    ]
    lists: dict[str, list[dict[str, Any]]] = {
        "cards": cards[:MAX_ITEMS],
        "sections": sections[:MAX_ITEMS],
        "subjects": subjects[:MAX_ITEMS],
        "question_types": types[:MAX_ITEMS],
        "questions": questions,
        "documents": documents[:MAX_DOCUMENTS],
    }
    _fit(lists)
    return {
        "user_id": user_id,
        "subject_id": subject_id,
        "command": command,
        "today": today,
        **lists,
    }


def _outline(session: Session, user_id: uuid.UUID, subject_id: uuid.UUID) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    repo = DocSectionRepository(session, user_id)
    for document in DocumentRepository(session, user_id).of_subject(subject_id):
        for section in repo.of_document(document.id):
            out.append({"id": section.id, "title": _title(section.title, "Mục")})
    return out


def _fit(lists: dict[str, list[dict[str, Any]]]) -> None:
    """Under the parser's total: the longest lists lose their tail first."""
    while sum(len(i["title"]) for items in lists.values() for i in items) > MAX_TOTAL:
        longest = max(lists.values(), key=len)
        longest.pop()
