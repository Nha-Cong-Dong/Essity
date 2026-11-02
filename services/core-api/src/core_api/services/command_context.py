"""What the command bar tells the parser (T9.2e, ADR-0030, US-18 AC7): ids and titles, never the
text of a document or a card. Cards and sections go in the order the screen shows them (T9.1 Y1:
the model reads "the second card" by position): sections in outline order document by document,
cards by the section that holds them (outline order, then oldest first), the ones in no section
last. Each list is cut at the parser's limits; a title is cut to the parser's length."""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from core_api.db.models import DocSection, KnowledgeUnit
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


def group_by_section(
    sections: Sequence[DocSection],
    units: Sequence[KnowledgeUnit],
    links: Sequence[tuple[uuid.UUID, uuid.UUID]],
) -> list[tuple[DocSection | None, list[KnowledgeUnit]]]:
    """The cards as the by-section screen shows them (T7.12d): one group per section that holds
    a card (the order `DraftRepository.by_section` gives), a card in several sections in each,
    the cards in none last under `None`. The screen and the command bar both read this, so "the
    second card" is the same card to the learner and to the parser."""
    members: dict[uuid.UUID, set[uuid.UUID]] = {}
    for unit_id, section_id in links:
        members.setdefault(section_id, set()).add(unit_id)
    groups: list[tuple[DocSection | None, list[KnowledgeUnit]]] = [
        (sec, [u for u in units if u.id in members.get(sec.id, set())]) for sec in sections
    ]
    placed = {unit_id for unit_id, _ in links}
    loose = [u for u in units if u.id not in placed]
    if loose:
        groups.append((None, loose))
    return groups


def cards_in_display_order(
    groups: Sequence[tuple[DocSection | None, list[KnowledgeUnit]]],
) -> list[KnowledgeUnit]:
    """The screen's cards read top to bottom, each once (at its first place)."""
    seen: set[uuid.UUID] = set()
    flat: list[KnowledgeUnit] = []
    for _, units in groups:
        for unit in units:
            if unit.id not in seen:
                seen.add(unit.id)
                flat.append(unit)
    return flat


def build_parse_payload(
    session: Session, user_id: uuid.UUID, subject_id: uuid.UUID, command: str, today: date
) -> dict[str, Any]:
    """The request body for ai-service. The subject must be this user's (the caller checks)."""
    drafts = DraftRepository(session, user_id)
    by_section, units, links = drafts.by_section(subject_id)
    sections = _outline(session, user_id, subject_id)
    ordered = cards_in_display_order(group_by_section(by_section, units, links))
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
