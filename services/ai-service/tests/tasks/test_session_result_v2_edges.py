"""session-result.v2, edges the tester added (T7.6; US-02 AC10): a draft's quote_hash must be the
hash of its own first quote, so a writer cannot pair a stable key with another quote."""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai_service.messaging.session_result_v2 import SessionResultV2, draft_key, quote_hash

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
    drafts = []
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
