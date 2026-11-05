"""FIX-CHUNK: one broken unit is dropped by rule name; the rest of the answer is kept.

Before, one unit with a bad field refused the whole answer (`schema`) and both attempts were
spent, so a session with one odd unit made no card at all (QA-FINAL 05/11).
"""

import json
import logging
from typing import Any

import pytest

from ai_service.tasks.chunk_units import ChunkInvalidError, chunk_units
from tests.chunk_units.helpers import Q2, FakeAsk, output, request, unit_json

CANARY = "CANARY7c1e"
LONG_TITLE = "one two three four five six seven eight nine ten eleven"


def good() -> dict[str, Any]:
    return unit_json(title="Krebs", anchors=[("D1.p2", Q2)])


# Red when: a unit with a bad kind refuses the whole answer instead of only itself.
def test_fix_chunk_bad_unit_dropped_rest_kept() -> None:
    ask = FakeAsk(output(unit_json(kind="essay"), good()))
    result = chunk_units(request(), ask)
    assert [u.title for u in result.new_units] == ["Krebs"]
    assert [(d.kind, d.reason) for d in result.dropped] == [("unit", "schema")]
    assert len(ask.prompts) == 1


# Red when: a title over 10 words refuses the whole answer instead of only that unit.
def test_fix_chunk_long_title_dropped_rest_kept() -> None:
    ask = FakeAsk(output(unit_json(title=LONG_TITLE), good()))
    result = chunk_units(request(), ask)
    assert [u.title for u in result.new_units] == ["Krebs"]
    assert [(d.kind, d.reason) for d in result.dropped] == [("unit", "title_words")]


# Red when: a summary over the cap refuses the whole answer.
def test_fix_chunk_long_summary_dropped_rest_kept() -> None:
    ask = FakeAsk(output(unit_json(summary="x" * 601), good()))
    result = chunk_units(request(), ask)
    assert [u.title for u in result.new_units] == ["Krebs"]
    assert [d.reason for d in result.dropped] == ["schema"]


# Red when: an answer where EVERY unit broke a rule counts as a result: no retry is made.
def test_fix_chunk_every_unit_broken_is_still_a_violation() -> None:
    ask = FakeAsk(output(unit_json(kind="essay"), unit_json(title=LONG_TITLE)))
    with pytest.raises(ChunkInvalidError):
        chunk_units(request(), ask)
    assert len(ask.prompts) == 2


# Red when: the log names no field (the QA log said only `schema`), or carries model text.
def test_fix_chunk_log_names_field_and_type_not_text(caplog: pytest.LogCaptureFixture) -> None:
    bad = unit_json(title=CANARY, kind=CANARY)
    bad[CANARY] = CANARY  # a key the model made up: its name is model text too
    with caplog.at_level(logging.DEBUG):
        chunk_units(request(), FakeAsk(output(bad, good())))
    [record] = [r for r in caplog.records if r.getMessage() == "chunk unit dropped"]
    errors = record.__dict__["errors"]
    assert {"loc": ["kind"], "type": "literal_error"} in errors
    assert {"loc": ["?"], "type": "extra_forbidden"} in errors
    assert all(CANARY not in str(vars(r)) for r in caplog.records)


# Red when: a whole-answer refusal (cut JSON) logs nothing about why.
def test_fix_chunk_envelope_refusal_logs_error_types(caplog: pytest.LogCaptureFixture) -> None:
    cut = '{"units": [' + json.dumps(good())
    with caplog.at_level(logging.DEBUG), pytest.raises(ChunkInvalidError):
        chunk_units(request(), FakeAsk(cut))
    records = [r for r in caplog.records if r.getMessage() == "chunk output refused"]
    assert [r.__dict__.get("errors") for r in records] == [
        [{"loc": [], "type": "json_invalid"}]
    ] * 2
