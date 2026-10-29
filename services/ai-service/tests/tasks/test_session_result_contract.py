"""contracts/files/session-result.v1: its examples say what the schema accepts and refuses
(T4.16b)."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

FILES = Path(__file__).resolve().parents[4] / "contracts" / "files"
SCHEMA: Any = Draft202012Validator(
    json.loads((FILES / "session-result.v1.schema.json").read_text(encoding="utf-8"))
)
EXAMPLES = sorted((FILES / "examples").glob("session-result.v1*.json"))


def test_the_examples_are_found() -> None:
    assert len(EXAMPLES) == 6


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_examples_match_their_name(path: Path) -> None:
    errors = list(SCHEMA.iter_errors(json.loads(path.read_text(encoding="utf-8"))))
    assert (errors != []) == ("invalid" in path.name.removeprefix("session-result.v1"))


def _example() -> dict[str, Any]:
    return json.loads((FILES / "examples" / "session-result.v1.json").read_text(encoding="utf-8"))


def _errors(question: dict[str, Any]) -> list[Any]:
    body = _example()
    body["questions"] = [question]
    return list(SCHEMA.iter_errors(body))


def test_a_question_names_its_units_in_a_list() -> None:
    question = _example()["questions"][0]
    assert isinstance(question["unit_ids"], list)
    assert _errors(question) == []


@pytest.mark.parametrize("level", [1, 2, 3])
def test_levels_one_to_three_are_accepted(level: int) -> None:
    assert _errors(_example()["questions"][0] | {"level": level}) == []


def test_level_four_is_refused() -> None:
    assert _errors(_example()["questions"][0] | {"level": 4}) != []


def test_empty_unit_ids_are_refused() -> None:
    assert _errors(_example()["questions"][0] | {"unit_ids": []}) != []


def test_duplicate_unit_ids_are_refused() -> None:
    unit = _example()["questions"][0]["unit_ids"][0]
    assert _errors(_example()["questions"][0] | {"unit_ids": [unit, unit]}) != []


def test_the_legacy_unit_id_is_refused() -> None:
    question = _example()["questions"][0]
    assert _errors(question | {"unit_id": question["unit_ids"][0]}) != []
