"""session-result.v2, edges the tester added (T7.6; US-02 AC10): a draft's quote_hash must be the
hash of its own first quote, so a writer cannot pair a stable key with another quote."""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from core_api.messaging.session_result_v2 import SessionResultV2, draft_key, quote_hash

EXAMPLE = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "files"
    / "examples"
    / "session-result.v2.json"
)


def body() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_quote_hash_of_another_quote_is_refused_even_with_a_matching_key() -> None:
    # Red when: only draft_key is checked against quote_hash, never quote_hash against the
    # anchor's quote (a retry could then keep a key while the quote changes underneath).
    result = body()
    draft = result["drafts"][0]
    other = "ab" * 32
    draft["quote_hash"] = other
    draft["draft_key"] = draft_key(uuid.UUID(result["study_session_id"]), other)
    with pytest.raises(ValidationError, match="quote_hash"):
        SessionResultV2.model_validate_json(json.dumps(result))


def test_the_same_quote_in_another_session_has_another_key() -> None:
    # Red when: draft_key does not depend on the session (two sessions would share drafts).
    result = body()
    draft = result["drafts"][0]
    assert draft_key(uuid.UUID(int=7), draft["quote_hash"]) != draft_key(
        uuid.UUID(int=8), draft["quote_hash"]
    )
    result["study_session_id"] = str(uuid.UUID(int=7))
    with pytest.raises(ValidationError, match="draft_key"):
        SessionResultV2.model_validate_json(json.dumps(result))
    draft["draft_key"] = draft_key(uuid.UUID(int=7), draft["quote_hash"])
    assert (
        SessionResultV2.model_validate_json(json.dumps(result)).drafts[0].draft_key
        == (draft["draft_key"])
    )


def test_a_refused_result_never_echoes_the_quote_text() -> None:
    # Red when: a ValidationError carries the input, so quote_text (user content) reaches logs.
    result = body()
    quote = result["drafts"][0]["anchors"][0]["quote_text"]
    result["drafts"][0]["draft_key"] = "0" * 64
    with pytest.raises(ValidationError) as error:
        SessionResultV2.model_validate_json(json.dumps(result))
    assert quote not in str(error.value)


def test_a_refused_anchor_never_echoes_the_quote_text() -> None:
    # Red when: hide_input_in_errors is dropped. The draft_key error above carries the whole
    # body, which pydantic truncates before the quote; a field error carries the value itself.
    result = body()
    quote = result["drafts"][0]["anchors"][0]["quote_text"]
    result["drafts"][0]["anchors"][0]["note"] = quote
    with pytest.raises(ValidationError) as error:
        SessionResultV2.model_validate_json(json.dumps(result))
    assert quote not in str(error.value)


def test_more_than_200_drafts_is_refused() -> None:
    # Red when: the drafts ceiling (schema maxItems 200) is lifted in the model, so one result
    # file can carry an unbounded number of drafts for the learner to review.
    result = body()
    template = result["drafts"][0]
    session = uuid.UUID(result["study_session_id"])
    drafts: list[Any] = []
    for i in range(201):
        draft = json.loads(json.dumps(template))
        draft["anchors"][0]["quote_text"] = f"quote {i}"
        draft["quote_hash"] = quote_hash(f"quote {i}")
        draft["draft_key"] = draft_key(session, draft["quote_hash"])
        drafts.append(draft)
    result["drafts"] = drafts[:200]
    assert len(SessionResultV2.model_validate_json(json.dumps(result)).drafts) == 200
    result["drafts"] = drafts
    with pytest.raises(ValidationError):
        SessionResultV2.model_validate_json(json.dumps(result))


def test_a_number_written_as_text_is_refused() -> None:
    # Red when: the model is not strict, so "3" passes as an anchor offset and a writer's type
    # error reaches the learner's drafts instead of failing the result.
    result = body()
    result["drafts"][0]["anchors"][0]["start"] = str(result["drafts"][0]["anchors"][0]["start"])
    with pytest.raises(ValidationError):
        SessionResultV2.model_validate_json(json.dumps(result))


# --- Round 2 (tester): the model refuses what the schema refuses, field by field (AC10) -------

SCHEMA = EXAMPLE.parents[1] / "session-result.v2.schema.json"


def _set(path: str, value: Any) -> dict[str, Any]:
    result = body()
    node: Any = result
    *steps, last = path.split(".")
    for step in steps:
        node = node[int(step)] if step.isdigit() else node[step]
    node[int(last) if last.isdigit() else last] = value
    return result


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("drafts.0.title", ""),
        ("drafts.0.title", "t" * 201),
        ("drafts.0.kind", "opinion"),
        ("drafts.0.anchors.0.page_no", 0),
        ("drafts.0.anchors.0.start", -1),
        ("drafts.0.anchors.0.source", "web"),
        ("dropped.drafts", -1),
        ("skipped.0.reason", "blurry"),
        ("skipped.0.kind", "slide"),
        ("version", 3),
    ],
)
def test_a_field_out_of_its_schema_is_refused_by_the_model_too(path: str, value: Any) -> None:
    # Red when: one field constraint of the model drifts from the schema (a length, a minimum or
    # an enum), so an LLM-written result the contract refuses still reaches the learner.
    result = _set(path, value)
    validator: Any = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    assert not validator.is_valid(result)
    with pytest.raises(ValidationError):
        SessionResultV2.model_validate_json(json.dumps(result))


def test_quote_hash_is_of_the_first_anchor_not_another() -> None:
    # Red when: the quote_hash rule reads any anchor but the first (the key would then move when
    # the writer reorders anchors).
    result = body()
    draft = result["drafts"][0]
    second = json.loads(json.dumps(draft["anchors"][0]))
    second["quote_text"] = "another quote"
    draft["anchors"].insert(0, second)
    with pytest.raises(ValidationError, match="quote_hash"):
        SessionResultV2.model_validate_json(json.dumps(result))
    draft["anchors"].reverse()
    assert len(SessionResultV2.model_validate_json(json.dumps(result)).drafts[0].anchors) == 2
