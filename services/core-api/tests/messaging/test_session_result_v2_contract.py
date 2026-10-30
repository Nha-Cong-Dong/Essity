"""contracts/files/session-result.v2 and submission-context.v1, checked from core-api's side
(T7.6; US-02 AC3, AC10). Reads the schemas and examples from `contracts/`, never imports the other
service (ADR-0003)."""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from core_api.messaging.session_result_v2 import (
    SessionResultV2,
    draft_key,
    parse_result,
    quote_hash,
)

FILES = Path(__file__).resolve().parents[4] / "contracts" / "files"
EXAMPLES = FILES / "examples"


def schema(name: str) -> Any:
    return Draft202012Validator(
        json.loads((FILES / f"{name}.schema.json").read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    )


def example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


V2 = sorted(EXAMPLES.glob("session-result.v2*.json"))
CONTEXT = sorted(EXAMPLES.glob("submission-context.v1*.json"))


def test_examples_are_found() -> None:
    assert len(V2) == 5 and len(CONTEXT) == 3


@pytest.mark.parametrize("path", V2, ids=lambda p: p.name)
def test_v2_examples_valid_and_invalid_per_schema(path: Path) -> None:
    # Red when: the schema takes an `invalid-*` example or refuses the valid one.
    body = json.loads(path.read_text(encoding="utf-8"))
    assert (not schema("session-result.v2").is_valid(body)) == ("invalid-" in path.name)


@pytest.mark.parametrize("path", CONTEXT, ids=lambda p: p.name)
def test_context_examples_valid_and_invalid_per_schema(path: Path) -> None:
    body = json.loads(path.read_text(encoding="utf-8"))
    assert (not schema("submission-context.v1").is_valid(body)) == ("invalid-" in path.name)


@pytest.mark.parametrize("path", V2, ids=lambda p: p.name)
def test_models_match_schema_v2(path: Path) -> None:
    # Red when: core-api's model accepts an `invalid-*` example or refuses the valid one.
    try:
        parse_result(path.read_bytes())
        accepted = True
    except ValidationError:
        accepted = False
    assert accepted == ("invalid-" not in path.name)


def test_draft_key_is_sha256_of_session_and_quote_hash() -> None:
    # Red when: the formula drifts from the one in the contract (AC10).
    body = example("session-result.v2")
    draft = body["drafts"][0]
    assert draft["quote_hash"] == quote_hash(draft["anchors"][0]["quote_text"])
    assert draft["draft_key"] == draft_key(uuid.UUID(body["study_session_id"]), draft["quote_hash"])


def test_quote_hash_folds_unicode_form_and_whitespace() -> None:
    assert quote_hash("  Định  tuyến" + chr(10) + " tĩnh ") == quote_hash("Định tuyến tĩnh")
    assert quote_hash("e" + chr(0x301)) == quote_hash(chr(0xE9))
    assert quote_hash("a") != quote_hash("b")


def test_result_v2_rejects_duplicate_draft_key() -> None:
    # Red when: two drafts with one key are taken (a retry would double the draft).
    body = example("session-result.v2")
    body["drafts"].append(dict(body["drafts"][0]))
    with pytest.raises(ValidationError, match="repeats"):
        SessionResultV2.model_validate_json(json.dumps(body))


def test_result_v2_rejects_a_key_that_is_not_the_formula() -> None:
    body = example("session-result.v2")
    body["drafts"][0]["draft_key"] = "0" * 64
    with pytest.raises(ValidationError):
        SessionResultV2.model_validate_json(json.dumps(body))
