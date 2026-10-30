"""Requests and outputs for the /v1/parse-command tests."""

import json
import uuid
from typing import Any

TODAY = "2026-11-04"  # a Wednesday


def items(prefix: str, count: int) -> list[dict[str, str]]:
    return [{"id": str(uuid.uuid4()), "title": f"{prefix} {n}"} for n in range(1, count + 1)]


def body(command: str = "gộp thẻ 2 và 5", **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "user_id": str(uuid.uuid4()),
        "subject_id": str(uuid.uuid4()),
        "command": command,
        "today": TODAY,
        "cards": items("Thẻ", 6),
        "sections": items("Mục", 8),
        "subjects": items("Môn", 3),
        "question_types": items("Dạng", 3),
        "questions": items("Câu", 4),
        "documents": items("Tài liệu", 2),
    }
    values.update(overrides)
    return values


def output(**result: Any) -> str:
    return json.dumps({"result": result}, ensure_ascii=False)


MERGE = output(kind="card_merge", cards=["C2", "C5"])
UNCLEAR = output(kind="unclear", reason="ambiguous")
