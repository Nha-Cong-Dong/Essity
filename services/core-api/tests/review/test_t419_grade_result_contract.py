"""contracts/files/grade-result.v1 from core-api's side (T4.19): the examples are what its models
read, and what they refuse. ai-service checks the same files from the other side."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from core_api.clients.grade_contract import GRADE_RESULT

FILES = Path(__file__).resolve().parents[4] / "contracts" / "files"
SCHEMA: Any = Draft202012Validator(
    json.loads((FILES / "grade-result.v1.schema.json").read_text(encoding="utf-8"))
)
EXAMPLES = sorted((FILES / "examples").glob("grade-result.v1*.json"))


def test_the_examples_are_found() -> None:
    assert len(EXAMPLES) == 4


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_the_models_and_the_schema_agree_on_every_example(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    by_schema = SCHEMA.is_valid(json.loads(raw))
    try:
        GRADE_RESULT.validate_json(raw)
        by_model = True
    except ValidationError:
        by_model = False
    assert by_schema == by_model == ("invalid" not in path.name)
