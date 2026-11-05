"""FIX-CHUNK tester edges for the per-unit check (`chunk_units._units`, `error_shape`)."""

import json
import logging

import pytest

from ai_service.tasks.chunk_models import MAX_TITLE_WORDS, MAX_UNITS_OUT
from ai_service.tasks.chunk_units import ChunkInvalidError, chunk_units
from tests.chunk_units.helpers import Q2, FakeAsk, output, request, unit_json

CANARY = "CANARY9d2f"


# Red when: a title of exactly MAX_TITLE_WORDS words is dropped (`>` became `>=`).
def test_fix_chunk_title_at_the_word_limit_is_kept() -> None:
    title = " ".join(f"w{i}" for i in range(MAX_TITLE_WORDS))
    result = chunk_units(request(), FakeAsk(output(unit_json(title=title))))
    assert [u.title for u in result.new_units] == [title]
    assert result.dropped == []


# Red when: a broken anchor field is logged without its position (indexes redacted, or the
# anchor's own field names turned into "?"), or the made-up key's name or the quote leaks.
def test_fix_chunk_nested_error_keeps_positions_and_known_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bad = unit_json(anchors=[("D1.p1", "x" * 2001)])
    bad["anchors"][0][CANARY] = CANARY
    good = unit_json(title="Krebs", anchors=[("D1.p2", Q2)])
    with caplog.at_level(logging.DEBUG):
        result = chunk_units(request(), FakeAsk(output(bad, good)))
    assert [u.title for u in result.new_units] == ["Krebs"]
    [record] = [r for r in caplog.records if r.getMessage() == "chunk unit dropped"]
    errors = record.__dict__["schema_errors"]
    assert {"loc": ["anchors", 0, "quote"], "type": "string_too_long"} in errors
    assert {"loc": ["anchors", 0, "?"], "type": "extra_forbidden"} in errors
    assert all(CANARY not in str(vars(r)) for r in caplog.records)


# Red when: an answer with a key of its own beside `units` is taken (the envelope stopped being
# strict when units began to be checked one by one).
def test_fix_chunk_envelope_extra_key_refused() -> None:
    text = json.dumps({"units": [unit_json()], CANARY: 1})
    ask = FakeAsk(text)
    with pytest.raises(ChunkInvalidError):
        chunk_units(request(), ask)
    assert len(ask.prompts) == 2


# Red when: an answer over MAX_UNITS_OUT units is taken (the cap moved off `LlmUnit` lists
# onto the envelope and was lost).
def test_fix_chunk_envelope_over_unit_cap_refused() -> None:
    ask = FakeAsk(output(*[unit_json(title=f"U{i}") for i in range(MAX_UNITS_OUT + 1)]))
    with pytest.raises(ChunkInvalidError):
        chunk_units(request(), ask)


# Red when: a unit that is not an object (a bare string) crashes the check or is kept.
def test_fix_chunk_unit_not_an_object_refuses_the_answer() -> None:
    ask = FakeAsk(json.dumps({"units": [CANARY, unit_json()]}))
    with pytest.raises(ChunkInvalidError):
        chunk_units(request(), ask)
    assert len(ask.prompts) == 2


# Red when: an empty answer (`units: []`, nothing to make) is treated as broken and retried.
def test_fix_chunk_empty_answer_is_a_result_not_a_violation() -> None:
    ask = FakeAsk(output())
    result = chunk_units(request(), ask)
    assert result.new_units == [] and result.dropped == []
    assert len(ask.prompts) == 1
