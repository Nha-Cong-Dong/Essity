"""`toc.json` against `contracts/files/toc.v1.schema.json` (T4.9): ai-service is the writer."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

FILES = Path(__file__).resolve().parents[4] / "contracts" / "files"
SCHEMA: dict[str, Any] = json.loads((FILES / "toc.v1.schema.json").read_text(encoding="utf-8"))


def valid(instance: Any) -> bool:
    return bool(cast(Any, Draft202012Validator(SCHEMA)).is_valid(instance))


def example(name: str) -> Any:
    return json.loads((FILES / "examples" / name).read_text(encoding="utf-8"))


def test_the_example_is_valid_and_the_invalid_ones_are_not() -> None:
    assert valid(example("toc.v1.json"))
    assert not valid(example("toc.v1.invalid-page-from-zero.json"))
    assert not valid(example("toc.v1.invalid-missing-page.json"))


@pytest.mark.parametrize("entries", [[]])
def test_an_empty_toc_is_valid(entries: list[Any]) -> None:
    assert valid({"entries": entries})
