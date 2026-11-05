"""CARDS-V3 tester edges: per-document caps of the outline a submission context carries."""

import uuid
from types import SimpleNamespace
from typing import Any

from core_api.domain.submission_outline import MAX_SECTIONS, MAX_TITLE, outline_for_context


def _section(document: uuid.UUID, ord_: int, title: str) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        document_id=document,
        parent_id=None,
        ord=ord_,
        title=title,
        first_page=ord_ + 1,
        last_page=ord_ + 1,
        excluded=False,
    )


def test_one_long_document_is_capped_at_max_sections() -> None:
    # Red when: a book with hundreds of short sections passes whole (the byte cap alone lets ~1500
    # short rows through), past the 300 the contract allows, so ai-service refuses the context.
    d = uuid.uuid4()
    rows = [_section(d, n, f"{n}") for n in range(MAX_SECTIONS + 100)]
    [doc] = outline_for_context([d], {}, rows)
    assert len(doc["sections"]) == MAX_SECTIONS


def test_a_long_title_is_cut_to_max_title() -> None:
    # Red when: a section title longer than the contract's 120 characters goes out as it is, and
    # the whole context (every mention) is refused by ai-service.
    d = uuid.uuid4()
    [doc] = outline_for_context([d], {}, [_section(d, 0, "Mục rất dài " * 40)])
    assert len(doc["sections"][0]["title"]) == MAX_TITLE
