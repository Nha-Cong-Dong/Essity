"""Builders of ai-service's result file for the T4.17 tests (session-result.v1)."""

import json
import uuid
from typing import Any


def anchor(document_id: uuid.UUID | None, **over: Any) -> dict[str, Any]:
    return {
        "source": "document",
        "document_id": None if document_id is None else str(document_id),
        "page_no": 3,
        "start": 0,
        "end": 12,
        "quote_text": "Một câu trích.",
    } | over


def unit(unit_id: uuid.UUID, document_id: uuid.UUID | None, **over: Any) -> dict[str, Any]:
    return {
        "unit_id": str(unit_id),
        "title": f"Mảnh {str(unit_id)[:4]}",
        "summary": "Tóm tắt.",
        "kind": "concept",
        "section_id": None,
        "lineage": [],
        "single_source": True,
        "anchors": [anchor(document_id)],
    } | over


def question(unit_ids: list[uuid.UUID], level: int = 1, **over: Any) -> dict[str, Any]:
    return {
        "unit_ids": [str(u) for u in unit_ids],
        "level": level,
        "prompt": f"Nêu ý chính {unit_ids[0]}.",
        "reference_answer": "Ý chính.",
        "rubric": "Nêu đúng ý chính.",
    } | over


def result(session_id: uuid.UUID, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "version": 1,
        "study_session_id": str(session_id),
        "units": [],
        "merges": [],
        "questions": [],
        "dropped": {"anchors": 0, "units": 0, "questions": 0},
        "skipped": [],
    }
    return base | over


def encode(body: dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode()
