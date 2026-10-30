"""T9.1 (US-18 AC2, AC3, AC6): the fake parser (local and test) through the same checks."""

import datetime
import uuid

import pytest

from ai_service.commands.schema import ParseCommandRequest
from ai_service.tasks.parse_command import (
    Labels,
    build_llm_request,
    check_output,
    fake_parse,
)
from tests.commands.helpers import TODAY, body

TODAY_D = datetime.date.fromisoformat(TODAY)
SUBJECTS = [
    {"id": str(uuid.uuid4()), "title": "Mạng máy tính"},
    {"id": str(uuid.uuid4()), "title": "Toán"},
]


def parse(command: str) -> dict[str, object]:
    request = ParseCommandRequest.model_validate(body(command, subjects=SUBJECTS))
    labels = Labels.of(request)
    llm = build_llm_request(request, labels, run_id=uuid.uuid4(), attempt=1, nonce="n0nce")
    return check_output(fake_parse(llm), labels, TODAY_D).model_dump(mode="json")


def test_merge() -> None:
    # US-18 AC2 (cards).
    assert parse("gộp thẻ 2 và 5")["kind"] == "card_merge"


def test_mark_studied_and_not_studied() -> None:
    # US-18 AC2 (syllabus).
    assert parse("đánh dấu mục 3 đã học")["studied"] is True
    assert parse("mục 3 và 4 chưa học")["studied"] is False


def test_only_subject_ends_on_sunday() -> None:
    # US-18 AC2 (study suggestions).
    result = parse("tuần này chỉ học môn Mạng máy tính")
    assert (result["kind"], result["until"]) == ("suggest_only_subject", "2026-11-08")


@pytest.mark.parametrize(
    ("command", "reason"),
    [
        ("xóa thẻ 2", "unsupported"),
        ("reset lịch ôn", "unsupported"),
        ("đổi tài khoản", "unsupported"),
        ("gộp thẻ 2 và 99", "unknown_target"),
        ("hôm nay trời đẹp", "ambiguous"),
    ],
)
def test_unclear_never_guesses(command: str, reason: str) -> None:
    # US-18 AC3 (unclear), AC6 (unsupported: delete, reset, account).
    assert parse(command) == {"kind": "unclear", "reason": reason}
