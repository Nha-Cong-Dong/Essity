"""Requests for /v1/grade tests."""

import uuid
from typing import Any


def anchor(text: str = "TCP bắt tay ba bước: SYN, SYN-ACK, ACK.") -> dict[str, Any]:
    return {"anchor_id": str(uuid.uuid4()), "quote_text": text}


def unit(title: str = "Bắt tay ba bước", *anchors: dict[str, Any]) -> dict[str, Any]:
    return {"unit_id": str(uuid.uuid4()), "title": title, "anchors": list(anchors) or [anchor()]}


def grade_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "user_id": str(uuid.uuid4()),
        "subject_id": str(uuid.uuid4()),
        "attempt_id": str(uuid.uuid4()),
        "question": {
            "text": "TCP mở kết nối thế nào?",
            "rubric": "Nêu đủ ba bước.",
            "reference_answer": "Bắt tay ba bước: SYN, SYN-ACK, ACK.",
        },
        "answer": "Client gửi SYN, server trả SYN-ACK, client gửi ACK.",
        "units": [unit()],
    }
    body.update(overrides)
    return body
