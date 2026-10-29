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
    assert len(EXAMPLES) == 2


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_examples_match_their_name(path: Path) -> None:
    errors = list(SCHEMA.iter_errors(json.loads(path.read_text(encoding="utf-8"))))
    assert (errors != []) == ("invalid" in path.name.removeprefix("session-result.v1"))
