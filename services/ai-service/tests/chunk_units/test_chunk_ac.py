"""US-02b AC1, AC3, AC4, AC5 through `chunk_units` with a fake model."""

import unicodedata
import uuid

from ai_service.tasks.chunk_models import ExistingUnit
from ai_service.tasks.chunk_units import chunk_units

from .helpers import NOTES, P1, P2, Q1, Q2, FakeAsk, output, request, unit_json

NOTE_QUOTE = "ty the la noi hop ho hap te bao"


def test_every_quote_in_page_text_AC3() -> None:
    req = request()
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", Q1), ("D1.p2", Q2)])))
    result = chunk_units(req, ask)
    assert len(result.new_units) == 1
    pages = {1: P1, 2: P2}
    for anchor in result.new_units[0].anchors:
        assert anchor.page_no is not None
        text = pages[anchor.page_no]
        assert text[anchor.start : anchor.end] == anchor.quote_text
        assert anchor.document_id == req.documents[0].document_id


def test_fabricated_quote_dropped_AC3() -> None:
    ask = FakeAsk(
        output(unit_json(anchors=[("D1.p1", Q1), ("D1.p1", "chloroplasts make sugar from light")]))
    )
    result = chunk_units(request(), ask)
    assert len(result.new_units[0].anchors) == 1
    assert [d.reason for d in result.dropped] == ["quote_not_found"]
    assert result.dropped_anchors == 1


def test_unit_without_valid_anchor_dropped_AC3() -> None:
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", "this text is nowhere in the page")])))
    result = chunk_units(request(), ask)
    assert result.new_units == []
    assert result.dropped_units == 1


def test_quote_from_other_page_dropped() -> None:
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", Q2)])))
    assert chunk_units(request(), ask).new_units == []


def test_offsets_refer_to_original_text() -> None:
    page = unicodedata.normalize("NFD", "Ty thể là nơi\n\n  hô hấp   tế bào, tạo nhiều ATP.")
    quote = unicodedata.normalize("NFC", "Ty thể là nơi hô hấp tế bào")
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", quote)])))
    anchor = chunk_units(request([page], notes=None), ask).new_units[0].anchors[0]
    assert page[anchor.start : anchor.end] == anchor.quote_text
    assert anchor.start == 0


def test_quote_copied_from_escaped_text_matches_original() -> None:
    page = "Compare a < b and a > b: the sign of a - b decides it. R&D too."
    quote = "a &lt; b and a &gt; b: the sign of a - b"
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", quote)])))
    anchor = chunk_units(request([page], notes=None), ask).new_units[0].anchors[0]
    assert anchor.quote_text == "a < b and a > b: the sign of a - b"


def test_notes_anchor_AC5() -> None:
    ask = FakeAsk(output(unit_json(anchors=[("notes", NOTE_QUOTE)])))
    new = chunk_units(request(), ask).new_units[0]
    anchor = new.anchors[0]
    assert (anchor.source, anchor.page_no, anchor.document_id) == ("notes", None, None)
    assert NOTES[anchor.start : anchor.end] == anchor.quote_text
    assert new.single_source is True


def test_document_only_unit_flagged_single_source_AC5() -> None:
    new = chunk_units(request(), FakeAsk(output(unit_json()))).new_units[0]
    assert new.single_source is True


def test_two_sources_not_flagged_AC5() -> None:
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", Q1), ("notes", NOTE_QUOTE)])))
    new = chunk_units(request(), ask).new_units[0]
    assert new.single_source is False
    assert {a.source for a in new.anchors} == {"document", "notes"}


def test_single_source_computed_after_filtering_AC5() -> None:
    bad = "invented note text here ok"
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", Q1), ("notes", bad)])))
    assert chunk_units(request(), ask).new_units[0].single_source is True


def test_same_idea_notes_and_doc_gives_one_unit_many_anchors_AC4() -> None:
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", Q1), ("notes", NOTE_QUOTE)])))
    result = chunk_units(request(), ask)
    assert len(result.new_units) == 1
    assert len(result.new_units[0].anchors) == 2


def test_repeat_idea_adds_anchors_to_existing_AC4() -> None:
    existing = ExistingUnit(unit_id=uuid.uuid4(), title="Ty the", summary="Hop ho hap.")
    ask = FakeAsk(output(unit_json(merge_into="U1")))
    result = chunk_units(request(existing=[existing]), ask)
    assert result.new_units == []
    assert [m.existing_unit_id for m in result.merges] == [existing.unit_id]
    assert len(result.merges[0].anchors) == 1
    assert not hasattr(result.merges[0], "review_log")


def test_identical_title_merges_into_existing_AC4() -> None:
    existing = ExistingUnit(unit_id=uuid.uuid4(), title="  TY the ", summary="x")
    ask = FakeAsk(output(unit_json(title="Ty  the")))
    result = chunk_units(request(existing=[existing]), ask)
    assert result.new_units == []
    assert result.merges[0].existing_unit_id == existing.unit_id


def test_unit_fields_schema_AC1() -> None:
    new = chunk_units(request(), FakeAsk(output(unit_json(kind="formula")))).new_units[0]
    assert new.kind == "formula"
    assert len(new.title.split()) <= 10
    assert new.summary
    assert new.section_id is None
