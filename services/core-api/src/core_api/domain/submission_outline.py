"""The outline a submission context carries (CARDS-V3): titles and page positions of the
documents the learner mentioned, so ai-service can find the section a vague @mention means
("@Giáo trình phần 1.1.1" has no pages) without a call back. No text of the documents is in it.

Pure: built from the sections core already loaded for the mention resolver (the learner's own
subject). Sizes are capped here and again by the contract (`submission-context.v1`).
"""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

MAX_DOCUMENTS = 20
MAX_SECTIONS = 300
MAX_TITLE = 120
MAX_NAME = 200
MAX_DEPTH = 10


# A `DocSection` row (id, document_id, parent_id, ord, title, first_page, last_page).
SectionLike = Any


def _walk(
    children: Mapping[uuid.UUID | None, Sequence[SectionLike]],
    parent: uuid.UUID | None,
    depth: int,
    rows: list[dict[str, Any]],
) -> None:
    for s in children.get(parent, []):
        if len(rows) >= MAX_SECTIONS:
            return
        rows.append(
            {
                "section_id": str(s.id),
                "title": s.title[:MAX_TITLE],
                "first_page": s.first_page,
                "last_page": s.last_page,
                "depth": min(depth, MAX_DEPTH),
            }
        )
        _walk(children, s.id, depth + 1, rows)


def outline_for_context(
    document_ids: Sequence[uuid.UUID],
    names: Mapping[uuid.UUID, str],
    sections: Sequence[SectionLike],
) -> list[dict[str, Any]]:
    """One entry per distinct document, in the order given, sections in tree order (parent before
    children, siblings by `ord`) with their depth."""
    out: list[dict[str, Any]] = []
    for document_id in list(dict.fromkeys(document_ids))[:MAX_DOCUMENTS]:
        mine = [s for s in sections if s.document_id == document_id]
        children: dict[uuid.UUID | None, list[SectionLike]] = {}
        for s in mine:
            children.setdefault(s.parent_id, []).append(s)
        for group in children.values():
            group.sort(key=lambda s: (s.ord, str(s.id)))
        rows: list[dict[str, Any]] = []

        _walk(children, None, 0, rows)
        out.append(
            {
                "document_id": str(document_id),
                "name": names.get(document_id, "")[:MAX_NAME],
                "sections": rows,
            }
        )
    return out
