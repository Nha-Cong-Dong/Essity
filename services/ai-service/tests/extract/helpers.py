"""Requests and model outputs for /v1/extract-session tests.

The book has 80 file pages; its printed numbers are 8 behind the file's (8 front pages in
roman numerals, then 1 on file page 9), like a real textbook (PRD 7.1b).
"""

import datetime
import json
import uuid
from collections.abc import Sequence
from typing import Any

from ai_service.tasks.extract_models import ExtractRequest
from ai_service.tasks.extract_session import Doc, normalize_documents

TODAY = datetime.date(2026, 10, 28)
ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii"]
BOOK_TOC = [
    ("Chương 1 Giới thiệu", 0, 9),
    ("1.1 Internet", 1, 10),
    ("Chương 3 Tầng giao vận", 0, 51),
    ("3.5 Connection Management", 1, 60),
    ("3.6 Congestion Control", 1, 70),
    ("Chương 4 Tầng mạng", 0, 75),
]


def printed_labels(count: int = 80) -> list[str]:
    return [ROMAN[p - 1] if p <= 8 else str(p - 8) for p in range(1, count + 1)]


def document(
    short_name: str = "giáo trình",
    *,
    page_count: int = 80,
    labels: list[str] | None | str = "book",
    toc: Sequence[tuple[str, int, int | None]] | None = None,
    last_end_page: int | None = None,
) -> dict[str, Any]:
    if labels == "book":
        labels = printed_labels(page_count)
    return {
        "document_id": str(uuid.uuid4()),
        "short_name": short_name,
        "page_count": page_count,
        "page_labels": labels,
        "toc": [
            {"title": title, "level": level, "page": page}
            for title, level, page in (BOOK_TOC if toc is None else toc)
        ],
        "last_end_page": last_end_page,
    }


def extract_body(description: str = "học giáo trình tr. 43-58", **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "user_id": str(uuid.uuid4()),
        "subject_id": str(uuid.uuid4()),
        "description": description,
        "today": TODAY.isoformat(),
        "documents": [document()],
    }
    body.update(overrides)
    return body


def docs_of(body: dict[str, Any]) -> list[Doc]:
    return normalize_documents(ExtractRequest.model_validate(body))


def rng(
    doc: str = "D1",
    kind: str = "pages",
    *,
    basis: str | None = "printed",
    from_page: int | None = 43,
    to_page: int | None = 58,
    from_section: str | None = None,
    to_section: str | None = None,
    depth: str = "deep",
) -> dict[str, Any]:
    return {
        "doc": doc,
        "kind": kind,
        "from_section": from_section,
        "to_section": to_section,
        "basis": basis,
        "from_page": from_page,
        "to_page": to_page,
        "depth": depth,
    }


def output(status: str = "proposed", **overrides: Any) -> str:
    value: dict[str, Any] = {
        "status": status,
        "studied_day": {"days_ago": None, "date": None},
        "ranges": [rng()] if status == "proposed" else [],
        "question": None,
        "reason": None,
        "candidates": [],
    }
    value.update(overrides)
    return json.dumps(value, ensure_ascii=False)
