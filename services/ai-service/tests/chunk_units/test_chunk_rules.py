"""Rules of the output check, limits, errors (T4.15, flow-expert 29/10, plan review)."""

import json
import logging
import uuid

import pytest

from ai_service.tasks.chunk_models import DocInput, ExistingUnit, PageInput
from ai_service.tasks.chunk_units import (
    ChunkInputTooLarge,
    ChunkInvalidError,
    chunk_units,
)

from .helpers import DOC_ID, P1, Q1, FakeAsk, output, request, unit_json


def _existing(n: int = 1) -> list[ExistingUnit]:
    return [ExistingUnit(unit_id=uuid.uuid4(), title=f"Unit {i}", summary="s") for i in range(n)]


def test_unknown_page_label_and_merge_label_rejected() -> None:
    ask = FakeAsk(
        output(
            unit_json(anchors=[("D9.p1", Q1)]),
            unit_json(title="Other idea", merge_into="U99"),
        )
    )
    result = chunk_units(request(), ask)
    assert [u.title for u in result.new_units] == ["Other idea"]  # unknown merge -> new unit
    assert result.merges == []
    assert result.dropped_units == 1


def test_quote_over_300_drops_only_that_anchor() -> None:
    long_page = ("word " * 100) + "tail"
    short = "Mitochondria are the site"
    anchors = [("D1.p1", long_page.strip()), ("D1.p2", short)]
    result = chunk_units(request([long_page, P1]), FakeAsk(output(unit_json(anchors=anchors))))
    assert len(result.new_units) == 1
    assert [a.quote_text for a in result.new_units[0].anchors] == [short]
    assert [d.reason for d in result.dropped] == ["quote_too_long"]


def test_multiple_matches_take_first_in_hinted_page() -> None:
    page = "the same long sentence here. the same long sentence here."
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", "the same long sentence here")])))
    anchor = chunk_units(request([page], notes=None), ask).new_units[0].anchors[0]
    assert (anchor.start, anchor.end) == (0, 27)


def test_two_output_units_merging_into_same_existing_give_one_addition() -> None:
    existing = _existing()
    ask = FakeAsk(output(unit_json(merge_into="U1"), unit_json(merge_into="U1", title="Again")))
    result = chunk_units(request(existing=existing), ask)
    assert len(result.merges) == 1
    assert len(result.merges[0].anchors) == 1  # same position, kept once


def test_lineage_only_known_existing_ids() -> None:
    existing = _existing(2)
    ask = FakeAsk(output(unit_json(lineage=["U2", "U7", "U2"])))
    new = chunk_units(request(existing=existing), ask).new_units[0]
    assert new.lineage == [existing[1].unit_id]


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        json.dumps({"units": [{"title": "t"}]}),
        output(unit_json(kind="essay")),
        output(unit_json(title="one two three four five six seven eight nine ten eleven")),
        json.dumps({"units": [], "extra": 1}),
        "x" * 60_001,
    ],
    ids=["not_json", "missing_fields", "kind", "title_words", "extra_field", "too_long"],
)
def test_schema_violation_retries_once_then_raises(bad: str) -> None:
    ask = FakeAsk(bad)
    with pytest.raises(ChunkInvalidError):
        chunk_units(request(), ask)
    assert len(ask.prompts) == 2


def test_retry_recovers() -> None:
    ask = FakeAsk("garbage", output(unit_json()))
    assert len(chunk_units(request(), ask).new_units) == 1
    assert len(ask.prompts) == 2


def test_empty_text_does_not_call_ask() -> None:
    ask = FakeAsk(output(unit_json()))
    result = chunk_units(request(["  \n "], notes="  "), ask)
    assert result.new_units == [] and ask.prompts == []


def test_too_many_units_output_rejected() -> None:
    ask = FakeAsk(output(*[unit_json(title=f"T{i}") for i in range(41)]))
    with pytest.raises(ChunkInvalidError):
        chunk_units(request(), ask)


def test_input_over_limit_rejected() -> None:
    page = PageInput(page_no=1, text="a" * 20_001)
    req = request().model_copy(
        update={"documents": [DocInput(document_id=DOC_ID, name="d", pages=[page])]}
    )
    ask = FakeAsk(output(unit_json()))
    with pytest.raises(ChunkInputTooLarge):
        chunk_units(req, ask)
    assert ask.prompts == []
    with pytest.raises(ChunkInputTooLarge):
        chunk_units(request(existing=_existing(201)), ask)
    with pytest.raises(ChunkInputTooLarge):
        chunk_units(request(notes="n" * 8001), ask)


def test_errors_and_logs_carry_no_source_text(caplog: pytest.LogCaptureFixture) -> None:
    canary = "CANARY-quote-text-9f3a"
    quote = canary + " is a long enough sentence"
    page = quote + " for the anchor"
    bad = output(unit_json(kind="essay", anchors=[("D1.p1", quote)]))
    with caplog.at_level(logging.DEBUG), pytest.raises(ChunkInvalidError) as info:
        chunk_units(request([page], notes=None), FakeAsk(bad))
    exc: BaseException | None = info.value
    while exc is not None:
        assert canary not in str(exc) and canary not in repr(exc)
        exc = exc.__cause__ or exc.__context__
    assert canary not in caplog.text

    anchors = [("D1.p1", quote), ("D1.p1", "zzz not in the page at all")]
    result = chunk_units(request([page], notes=None), FakeAsk(output(unit_json(anchors=anchors))))
    assert canary not in repr(result.dropped)
