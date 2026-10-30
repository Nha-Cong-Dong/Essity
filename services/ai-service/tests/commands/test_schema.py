"""T9.1, US-18 AC2, AC6, AC7: the fixed union and the request that carries ids and titles only."""

import uuid
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from ai_service.commands.schema import (
    MAX_TOTAL_TITLE_CHARS,
    OPERATIONS,
    REFS,
    Command,
    ParseCommandRequest,
)
from ai_service.tasks.parse_command import OUTPUT_SCHEMA
from tests.commands.helpers import body

EXPECTED = {
    "card_edit", "card_merge", "card_split", "card_add", "card_discard_draft", "card_add_idea",
    "section_set_pages", "section_exclude", "section_mark",
    "suggest_only_subject", "suggest_defer_subject",
    "question_set_type", "question_relink", "question_set_answer", "question_remove_from_practice",
    "unclear",
}  # fmt: skip


def test_the_union_is_exactly_the_adr_list() -> None:
    # Red when: an operation is added or dropped without this list (and ADR-0030) changing.
    assert set(OPERATIONS) == EXPECTED
    assert set(REFS) == EXPECTED


@pytest.mark.parametrize(
    "kind",
    [
        "card_delete",
        "delete_card",
        "subject_delete",
        "document_delete",
        "question_bank_delete",
        "fsrs_reset",
        "history_delete",
        "set_cost_cap",
        "account_update",
    ],
)
def test_never_by_command_operations_are_not_in_the_union(kind: str) -> None:
    # Red when: a destructive operation becomes parseable (AC6).
    assert kind not in OPERATIONS
    with pytest.raises(ValidationError):
        TypeAdapter(Command).validate_python({"kind": kind, "card": str(uuid.uuid4())})


def test_the_output_schema_offers_only_the_listed_kinds() -> None:
    variants = OUTPUT_SCHEMA["properties"]["result"]["anyOf"]
    kinds = {v["properties"]["kind"]["const"] for v in variants}
    assert kinds == EXPECTED
    assert all(v["additionalProperties"] is False for v in variants)


def test_request_refuses_document_text_and_unknown_fields() -> None:
    # Red when: a field for document text can be sent to the model (AC7).
    with pytest.raises(ValidationError):
        ParseCommandRequest.model_validate(body(document_text="chương 1 ..."))
    cards: list[dict[str, Any]] = [{"id": str(uuid.uuid4()), "title": "x", "content": "text"}]
    with pytest.raises(ValidationError):
        ParseCommandRequest.model_validate(body(cards=cards))


def _doc() -> dict[str, str]:
    return {"id": str(uuid.uuid4()), "title": "d"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"command": "   "},
        {"command": "x" * 501},
        {"command": "a\x00b"},
        {"cards": [{"id": str(uuid.uuid4()), "title": "x" * 121}]},
        {"cards": [{"id": str(uuid.uuid4()), "title": " "}]},
        {"documents": [{"id": "6f1d5a1e-0000-4000-8000-000000000001", "title": "d"}] * 2},
        {"cards": [_doc() for _ in range(201)]},
        {"documents": [_doc() for _ in range(51)]},
        {"today": "not a date"},
    ],
)
def test_request_limits(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ParseCommandRequest.model_validate(body(**overrides))


def test_total_title_size_is_bounded() -> None:
    def big() -> list[dict[str, str]]:
        return [{"id": str(uuid.uuid4()), "title": "x" * 120} for _ in range(200)]

    assert 5 * 200 * 120 > MAX_TOTAL_TITLE_CHARS
    with pytest.raises(ValidationError):
        ParseCommandRequest.model_validate(
            body(cards=big(), sections=big(), subjects=big(), questions=big(), question_types=big())
        )


def test_a_full_valid_request_is_accepted() -> None:
    ParseCommandRequest.model_validate(body())
