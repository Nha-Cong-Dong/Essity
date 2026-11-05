"""CARDS-V3: the outline of a submission context, as a pure function."""

import json
import uuid
from types import SimpleNamespace
from typing import Any

from core_api.domain.submission_outline import (
    MAX_DEPTH,
    MAX_DOCUMENTS,
    MAX_OUTLINE_BYTES,
    outline_for_context,
)


def section(document: uuid.UUID, parent: Any, ord_: int, title: str, **kw: Any) -> Any:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "document_id": document,
        "parent_id": parent,
        "ord": ord_,
        "title": title,
        "first_page": None,
        "last_page": None,
        "excluded": False,
    } | kw
    return SimpleNamespace(**values)


def test_tree_order_with_depth_and_siblings_by_ord() -> None:
    d = uuid.uuid4()
    a = section(d, None, 1, "B")
    b = section(d, None, 0, "A")
    child = section(d, b.id, 0, "A.1")
    [doc] = outline_for_context([d], {d: "Giáo trình"}, [a, child, b])
    assert [(s["title"], s["depth"]) for s in doc["sections"]] == [("A", 0), ("A.1", 1), ("B", 0)]
    assert doc["name"] == "Giáo trình"


def test_repeated_document_ids_count_once_and_documents_are_capped() -> None:
    ids = [uuid.uuid4() for _ in range(MAX_DOCUMENTS + 5)]
    out = outline_for_context(ids + ids[:3], {}, [])
    assert len(out) == MAX_DOCUMENTS


def test_depth_is_capped_and_excluded_sections_are_left_out() -> None:
    d = uuid.uuid4()
    parent = None
    chain: list[Any] = []
    for n in range(MAX_DEPTH + 4):
        s = section(d, parent, 0, f"t{n}")
        chain.append(s)
        parent = s.id
    chain.append(section(d, None, 5, "hidden", excluded=True))
    [doc] = outline_for_context([d], {}, chain)
    assert max(s["depth"] for s in doc["sections"]) == MAX_DEPTH
    assert "hidden" not in [s["title"] for s in doc["sections"]]


def test_total_bytes_are_capped_across_documents() -> None:
    ids = [uuid.uuid4() for _ in range(MAX_DOCUMENTS)]
    sections = [
        section(d, None, n, "ế" * 120, first_page=1, last_page=2) for d in ids for n in range(300)
    ]
    out = outline_for_context(ids, {}, sections)
    size = len(json.dumps(out, ensure_ascii=False).encode())
    assert size < MAX_OUTLINE_BYTES + 5_000
