"""The outline a submission context carries (CARDS-V3): titles and page positions of the
documents the learner mentioned, so ai-service can find the section a vague @mention means
("@Giáo trình phần 1.1.1" has no pages) without a call back. No text of the documents is in it.

Pure: built from the sections core already loaded for the mention resolver (the learner's own
subject). Sizes are capped here and again by the contract (`submission-context.v1`).
"""

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

MAX_DOCUMENTS = 20
MAX_SECTIONS = 300
MAX_TITLE = 120
MAX_NAME = 200
MAX_DEPTH = 10
# The context file is read by ai-service under a 1 MB cap, with the existing units in it: the
# outline never takes more than this many bytes (Vietnamese titles are ~2 bytes a letter).
MAX_OUTLINE_BYTES = 300_000


# A `DocSection` row (id, document_id, parent_id, ord, title, first_page, last_page).
SectionLike = Any


def _walk(
    children: Mapping[uuid.UUID | None, Sequence[SectionLike]],
    parent: uuid.UUID | None,
    depth: int,
    rows: list[dict[str, Any]],
    spent: list[int],
) -> None:
    for s in children.get(parent, []):
        if len(rows) >= MAX_SECTIONS or spent[0] >= MAX_OUTLINE_BYTES:
            return
        row = {
            "section_id": str(s.id),
            "title": s.title[:MAX_TITLE],
            "first_page": s.first_page,
            "last_page": s.last_page,
            "depth": min(depth, MAX_DEPTH),
        }
        spent[0] += len(json.dumps(row, ensure_ascii=False).encode())
        rows.append(row)
        _walk(children, s.id, depth + 1, rows, spent)


def outline_for_context(
    document_ids: Sequence[uuid.UUID],
    names: Mapping[uuid.UUID, str],
    sections: Sequence[SectionLike],
) -> list[dict[str, Any]]:
    """One entry per distinct document, in the order given, sections in tree order (parent before
    children, siblings by `ord`) with their depth."""
    out: list[dict[str, Any]] = []
    spent = [0]
    for document_id in list(dict.fromkeys(document_ids))[:MAX_DOCUMENTS]:
        # An excluded section is one the learner left out of the study: not offered to the model.
        mine = [s for s in sections if s.document_id == document_id and not s.excluded]
        children: dict[uuid.UUID | None, list[SectionLike]] = {}
        for s in mine:
            children.setdefault(s.parent_id, []).append(s)
        for group in children.values():
            group.sort(key=lambda s: (s.ord, str(s.id)))
        rows: list[dict[str, Any]] = []

        _walk(children, None, 0, rows, spent)
        out.append(
            {
                "document_id": str(document_id),
                "name": names.get(document_id, "")[:MAX_NAME],
                "sections": rows,
            }
        )
    return out
