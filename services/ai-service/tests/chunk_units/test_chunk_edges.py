"""Edge cases found by the T4.15 tester (mutation run 29/10): limits at the boundary, anchor
lookup corners, merge rules with real existing units, labels and ids across documents."""

import logging
import uuid

import pytest

from ai_service.tasks.chunk_models import ChunkRequest, DocInput, ExistingUnit, PageInput
from ai_service.tasks.chunk_units import ChunkInputTooLarge, ChunkInvalidError, chunk_units

from .helpers import DOC_ID, P1, P2, Q1, Q2, FakeAsk, output, request, unit_json

DOC2_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _docs(*docs: DocInput, notes: str | None = None, existing: list[ExistingUnit] | None = None):
    return ChunkRequest(documents=list(docs), notes_text=notes, existing_units=existing or [])


def _doc(pages: list[tuple[int, str]], doc_id: uuid.UUID = DOC_ID) -> DocInput:
    return DocInput(
        document_id=doc_id,
        name="d",
        pages=[PageInput(page_no=n, text=t) for n, t in pages],
    )


def _existing(*titles: str) -> list[ExistingUnit]:
    return [ExistingUnit(unit_id=uuid.uuid4(), title=t, summary="s") for t in titles]


# --- Input limits at the boundary ------------------------------------------------------------


def test_sixty_pages_accepted_sixty_one_rejected() -> None:
    # Red when: the page limit is dropped, moved off 60, or compared with >=.
    ask = FakeAsk(output())
    ok = _docs(_doc([(i, "page text") for i in range(1, 61)]))
    assert chunk_units(ok, ask).new_units == []
    over = _docs(_doc([(i, "page text") for i in range(1, 62)]))
    with pytest.raises(ChunkInputTooLarge) as info:
        chunk_units(over, ask)
    assert info.value.rule == "pages"
    assert len(ask.prompts) == 1  # the refused request never reached the model


def test_page_limit_counts_pages_across_documents() -> None:
    # Red when: the 60-page limit is checked per document instead of per request.
    a = _doc([(i, "x") for i in range(1, 32)])
    b = _doc([(i, "y") for i in range(1, 32)], doc_id=DOC2_ID)
    ask = FakeAsk(output())
    with pytest.raises(ChunkInputTooLarge) as info:
        chunk_units(_docs(a, b), ask)
    assert info.value.rule == "pages"
    assert ask.prompts == []


def test_total_chars_exactly_at_limit_accepted() -> None:
    # Red when: the total limit uses >=, or a 20000-char page is refused (>= on page_chars).
    pages = [(i, "a" * 20_000) for i in range(1, 11)]  # 200000 chars
    ask = FakeAsk(output())
    assert chunk_units(_docs(_doc(pages)), ask).new_units == []


def test_total_chars_counts_notes() -> None:
    # Red when: the total limit is dropped or ignores the notes (200000 pages + 1 note char).
    pages = [(i, "a" * 20_000) for i in range(1, 11)]
    ask = FakeAsk(output())
    with pytest.raises(ChunkInputTooLarge) as info:
        chunk_units(_docs(_doc(pages), notes="n"), ask)
    assert info.value.rule == "total_chars"
    assert ask.prompts == []


def test_input_limit_rules_named() -> None:
    # Red when: one of the per-field limits is dropped (the request goes to the model).
    ask = FakeAsk(output())
    with pytest.raises(ChunkInputTooLarge) as info:
        chunk_units(_docs(_doc([(1, "a" * 20_001)])), ask)
    assert info.value.rule == "page_chars"
    with pytest.raises(ChunkInputTooLarge) as info:
        chunk_units(_docs(_doc([(1, "a")]), notes="n" * 8_001), ask)
    assert info.value.rule == "notes_chars"
    with pytest.raises(ChunkInputTooLarge) as info:
        chunk_units(_docs(_doc([(1, "a")]), existing=_existing(*["t"] * 201)), ask)
    assert info.value.rule == "existing_units"
    assert ask.prompts == []


# --- Anchor lookup corners -------------------------------------------------------------------


def test_quote_of_exactly_300_chars_kept() -> None:
    # Red when: the quote cap is compared with >= (a 300-char quote is dropped).
    page = "start " + "c" * 300 + " end"
    quote = "c" * 300
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", quote)])))
    result = chunk_units(request([page], notes=None), ask)
    assert [a.quote_text for a in result.new_units[0].anchors] == [quote]
    assert result.dropped == []


def test_quote_with_surrounding_whitespace_anchors_on_the_words() -> None:
    # Red when: the quote is not stripped (leading space misses the page start, or the anchor
    # range swallows the space).
    quote = "  Mitochondria are the site  "
    anchor = (
        chunk_units(request(), FakeAsk(output(unit_json(anchors=[("D1.p1", quote)]))))
        .new_units[0]
        .anchors[0]
    )
    assert (anchor.start, anchor.quote_text) == (0, "Mitochondria are the site")


def test_literal_entity_text_on_page_unescaped_once() -> None:
    # The page really contains "&lt;", shown to the model as "&amp;lt;"; one unescape pass
    # gives back the page text. Red when: the quote is unescaped twice (or not at all).
    page = "In HTML you write &lt;b&gt; to show a bold tag literally."
    quote = "you write &amp;lt;b&amp;gt; to show a bold tag"
    result = chunk_units(
        request([page], notes=None), FakeAsk(output(unit_json(anchors=[("D1.p1", quote)])))
    )
    assert [a.quote_text for a in result.new_units[0].anchors] == [
        "you write &lt;b&gt; to show a bold tag"
    ]


def test_same_quote_twice_in_unit_kept_once() -> None:
    # Red when: anchors inside one unit are not deduplicated by position.
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", Q1), ("D1.p1", Q1 + " ")])))
    assert len(chunk_units(request(), ask).new_units[0].anchors) == 1


# --- Labels and ids across documents ---------------------------------------------------------


def test_page_label_uses_page_no_not_position() -> None:
    # Pages 3 and 7 (a page range of a longer PDF). Red when: labels follow list position, so
    # "D1.p7" misses or points at the wrong page.
    req = _docs(_doc([(3, P1), (7, P2)]))
    ask = FakeAsk(output(unit_json(anchors=[("D1.p7", Q2)])))
    anchor = chunk_units(req, ask).new_units[0].anchors[0]
    assert anchor.page_no == 7
    assert P2[anchor.start : anchor.end] == anchor.quote_text
    assert 'label="D1.p7"' in ask.prompts[0].user


def test_anchor_carries_its_own_document_id() -> None:
    # Red when: every anchor gets the first document's id.
    req = _docs(_doc([(1, P1)]), _doc([(1, P2)], doc_id=DOC2_ID))
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", Q1), ("D2.p1", Q2)])))
    anchors = chunk_units(req, ask).new_units[0].anchors
    assert [(a.document_id, a.page_no) for a in anchors] == [(DOC_ID, 1), (DOC2_ID, 1)]


# --- Merge rules with real existing units (AC4, ARCH §12) ------------------------------------


def test_unknown_merge_label_with_existing_units_is_new_unit_AC4() -> None:
    # Red when: an unknown label ("U9") is mapped onto some existing unit.
    existing = _existing("Unit one", "Unit two")
    ask = FakeAsk(output(unit_json(title="Other idea", merge_into="U9")))
    result = chunk_units(request(existing=existing), ask)
    assert result.merges == []
    assert [u.title for u in result.new_units] == ["Other idea"]


def test_merge_with_no_valid_anchor_adds_nothing_AC4() -> None:
    # Red when: a merge whose anchors are all fabricated still emits an (empty) addition.
    existing = _existing("Ty the")
    ask = FakeAsk(
        output(unit_json(merge_into="U1", anchors=[("D1.p1", "not anywhere in the page")]))
    )
    result = chunk_units(request(existing=existing), ask)
    assert result.merges == [] and result.new_units == []
    assert result.dropped_units == 1


def test_two_units_merging_into_same_existing_keep_all_anchors_AC4() -> None:
    # Red when: the second merge replaces the anchors of the first instead of adding to them.
    existing = _existing("Ty the")
    ask = FakeAsk(
        output(
            unit_json(merge_into="U1", anchors=[("D1.p1", Q1)]),
            unit_json(title="Again", merge_into="U1", anchors=[("D1.p2", Q2)]),
        )
    )
    result = chunk_units(request(existing=existing), ask)
    assert len(result.merges) == 1
    assert sorted(a.page_no or 0 for a in result.merges[0].anchors) == [1, 2]


def test_same_title_existing_units_first_wins_AC4() -> None:
    # Two existing units with the same title: the title safety net picks the first.
    # Red when: the last one wins.
    existing = _existing("Ty the", "ty THE")
    result = chunk_units(request(existing=existing), FakeAsk(output(unit_json(title="Ty the"))))
    assert [m.existing_unit_id for m in result.merges] == [existing[0].unit_id]


def test_two_document_pages_still_single_source_AC5() -> None:
    # AC5 flags one SOURCE (document vs notes), not one anchor. Red when: the flag counts
    # anchors or pages.
    ask = FakeAsk(output(unit_json(anchors=[("D1.p1", Q1), ("D1.p2", Q2)])))
    new = chunk_units(request(), ask).new_units[0]
    assert len(new.anchors) == 2
    assert new.single_source is True


def test_refusal_log_carries_rule_name_not_output(caplog: pytest.LogCaptureFixture) -> None:
    # The warning's `outcome` goes to structured logs. Red when: a violation carries model
    # output (here the title) instead of a rule name.
    canary = "CANARY9f3a"
    bad = output(unit_json(title=canary, kind="essay"))
    with caplog.at_level(logging.DEBUG), pytest.raises(ChunkInvalidError):
        chunk_units(request(), FakeAsk(bad))
    records = [r for r in caplog.records if r.getMessage() == "chunk output refused"]
    assert [getattr(r, "outcome", None) for r in records] == ["schema", "schema"]
    assert all(canary not in str(vars(r)) for r in caplog.records)


def test_valid_output_over_size_cap_refused() -> None:
    # Red when: the 60000-char cap is not checked before parsing (padding is valid JSON).
    padded = output(unit_json()) + " " * 60_001
    ask = FakeAsk(padded)
    with pytest.raises(ChunkInvalidError):
        chunk_units(request(), ask)
    assert len(ask.prompts) == 2


def test_input_models_hide_input_in_validation_errors() -> None:
    from pydantic import ValidationError

    from ai_service.tasks.chunk_models import PageInput

    with pytest.raises(ValidationError) as caught:
        PageInput(page_no=1, text="secret\x00learner text")
    assert "secret" not in str(caught.value)


def test_nul_in_llm_title_or_summary_is_a_schema_violation() -> None:
    from ai_service.tasks.chunk_units import ChunkInvalidError

    for field in ("title", "summary"):
        bad = unit_json(**{field: "ab\x00cd"})
        with pytest.raises(ChunkInvalidError):
            chunk_units(request(), FakeAsk(output(bad)))
