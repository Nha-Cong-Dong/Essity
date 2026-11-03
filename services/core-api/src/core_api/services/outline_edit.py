"""Merge and split of outline sections for the outline chat (E3, hackathon 04/11).

Plain functions on `doc_section` rows, no command log: the chat says what it did and the learner
can ask again in the other direction. A section that already has cards or questions linked is
never merged or split (nothing is re-pointed behind the learner's back). Titles are found by
their number ("1.2", "3") the way the learner reads them, optionally after "mục", "chương", ...
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core_api.db.models import DocSection, QuestionSection, UnitSection

MAX_PARTS = 10
_WORDS = "chương|chuong|phần|phan|mục|muc|bài|bai|chapter|section"


class EditRefused(Exception):
    """Why the edit did not run, as a sentence for the learner."""


@dataclass(frozen=True)
class Edit:
    reply: str
    changed: int


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold().strip()


def find_section(sections: list[DocSection], ref: str) -> DocSection:
    """The section whose title starts with `ref` as a number ("1.2" is not "1.20" or "1.2.1")."""
    ref = _fold(ref).strip(" .")
    pattern = re.compile(rf"^(?:(?:{_WORDS})\s*)?{re.escape(ref)}(?![\d]|\.\d)")
    found = [s for s in sections if pattern.match(_fold(s.title))]
    if not found:
        raise EditRefused(f"Mình không thấy mục “{ref}” trong đề cương.")
    if len(found) > 1:
        raise EditRefused(f"Có nhiều mục khớp với “{ref}”, bạn nói rõ hơn nhé.")
    return found[0]


def _subject_sections(
    session: Session, user_id: uuid.UUID, subject_id: uuid.UUID
) -> list[DocSection]:
    return list(
        session.scalars(
            select(DocSection)
            .where(DocSection.user_id == user_id, DocSection.subject_id == subject_id)
            .order_by(DocSection.document_id, DocSection.ord, DocSection.id)
        )
    )


def _linked(session: Session, user_id: uuid.UUID, section_id: uuid.UUID) -> bool:
    cards = session.scalar(
        select(func.count())
        .select_from(UnitSection)
        .where(UnitSection.user_id == user_id, UnitSection.section_id == section_id)
    )
    questions = session.scalar(
        select(func.count())
        .select_from(QuestionSection)
        .where(QuestionSection.user_id == user_id, QuestionSection.section_id == section_id)
    )
    return bool(cards or questions)


def _children_of(
    session: Session, user_id: uuid.UUID, document_id: uuid.UUID, parent: uuid.UUID | None
) -> list[DocSection]:
    same_parent = (
        DocSection.parent_id.is_(None) if parent is None else DocSection.parent_id == parent
    )
    return list(
        session.scalars(
            select(DocSection)
            .where(
                DocSection.user_id == user_id, DocSection.document_id == document_id, same_parent
            )
            .order_by(DocSection.ord, DocSection.id)
        )
    )


def _reindex(
    session: Session, user_id: uuid.UUID, document_id: uuid.UUID, parent: uuid.UUID | None
) -> None:
    for i, row in enumerate(_children_of(session, user_id, document_id, parent)):
        row.ord = i
    session.flush()


def merge_sections(
    session: Session, user_id: uuid.UUID, subject_id: uuid.UUID, refs: list[str]
) -> Edit:
    """Sibling sections into the first one: pages and weight add up, children move under it."""
    if len(refs) < 2:
        raise EditRefused("Bạn muốn gộp những mục nào? Ví dụ: “gộp mục 1.2 với 1.3”.")
    sections = _subject_sections(session, user_id, subject_id)
    picked = [find_section(sections, r) for r in refs]
    if len({s.id for s in picked}) != len(picked):
        raise EditRefused("Bạn nhắc cùng một mục hai lần.")
    first, rest = picked[0], picked[1:]
    if any(s.parent_id != first.parent_id or s.document_id != first.document_id for s in rest):
        raise EditRefused("Chỉ gộp được các mục cùng cấp, cùng nằm dưới một chương.")
    if any(_linked(session, user_id, s.id) for s in rest):
        raise EditRefused("Có mục đã gắn thẻ hoặc câu hỏi nên mình không gộp được.")
    for s in rest:
        first.weight += s.weight
        first.studied_weight += s.studied_weight
        if None not in (first.first_page, first.last_page, s.first_page, s.last_page):
            assert first.first_page and first.last_page and s.first_page and s.last_page
            first.first_page = min(first.first_page, s.first_page)
            first.last_page = max(first.last_page, s.last_page)
        for child in _children_of(session, user_id, s.document_id, s.id):
            child.parent_id = first.id
            child.ord += 10_000  # after the first's own children; reindexed below
        session.flush()
        session.delete(s)
        session.flush()
    _reindex(session, user_id, first.document_id, first.id)
    _reindex(session, user_id, first.document_id, first.parent_id)
    return Edit(f"Đã gộp {len(picked)} mục thành “{first.title}”.", len(picked))


def split_section(
    session: Session, user_id: uuid.UUID, subject_id: uuid.UUID, ref: str, parts: int | None
) -> Edit:
    """A section with child headings: the children take its place (the section goes). A section
    without: even page ranges, `parts` of them (2 by default)."""
    sections = _subject_sections(session, user_id, subject_id)
    target = find_section(sections, ref)
    if _linked(session, user_id, target.id):
        raise EditRefused("Mục này đã gắn thẻ hoặc câu hỏi nên mình không tách được.")
    children = _children_of(session, user_id, target.document_id, target.id)
    if children and parts is not None:
        raise EditRefused("Mục này đã có đề mục con; hãy nói “tách” không kèm số phần.")
    if children:
        siblings = _children_of(session, user_id, target.document_id, target.parent_id)
        at = siblings.index(target)
        order = [*siblings[:at], *children, *siblings[at + 1 :]]
        for child in children:
            child.parent_id = target.parent_id
        session.flush()
        title = target.title
        session.delete(target)
        session.flush()
        for i, row in enumerate(order):
            row.ord = i
        session.flush()
        return Edit(
            f"Đã tách “{title}” thành {len(children)} mục theo các đề mục con.", len(children)
        )
    n = parts or 2
    if not 2 <= n <= MAX_PARTS:
        raise EditRefused(f"Mình chỉ tách được từ 2 đến {MAX_PARTS} phần.")
    if target.first_page is None or target.last_page is None:
        raise EditRefused("Mục này không có số trang nên mình không chia được.")
    pages = target.last_page - target.first_page + 1
    if pages < n:
        raise EditRefused(f"Mục này chỉ có {pages} trang, không chia được {n} phần.")
    size, extra = divmod(pages, n)
    start = target.first_page
    title, weight, studied = target.title, target.weight, target.studied_weight
    ranges: list[tuple[int, int]] = []
    for i in range(n):
        end = start + size + (1 if i < extra else 0) - 1
        ranges.append((start, end))
        start = end + 1
    for sib in _children_of(session, user_id, target.document_id, target.parent_id):
        if sib.ord > target.ord:
            sib.ord += n - 1
    first_a, first_b = ranges[0]
    target.title = f"{title} (phần 1)"
    target.first_page, target.last_page = first_a, first_b
    target.weight, target.studied_weight = weight * (first_b - first_a + 1) / pages, studied / n
    for i, (a, b) in enumerate(ranges[1:], start=1):
        row = DocSection(
            subject_id=subject_id,
            document_id=target.document_id,
            parent_id=target.parent_id,
            ord=target.ord + i,
            title=f"{title} (phần {i + 1})",
            first_page=a,
            last_page=b,
            weight=weight * (b - a + 1) / pages,
            studied_weight=studied / n,
            unit=target.unit,
            source="user",
            excluded=target.excluded,
        )
        row.id = uuid.uuid4()
        row.user_id = user_id
        session.add(row)
    session.flush()
    return Edit(f"Đã tách “{title}” thành {n} phần theo số trang.", n)
