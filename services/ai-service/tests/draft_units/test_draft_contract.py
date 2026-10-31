"""T7.7: `draft_units` speaks the session-result.v2 vocabulary (US-02 AC10, US-02b AC3/AC4)."""

import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_service.messaging.session_result_v2 import draft_key, quote_hash
from ai_service.messaging.submission_context import SubmissionContext, parse_context
from ai_service.tasks.draft_units import DraftRequest, ScopedDoc, ScopedPage, draft_units
from tests.draft_units.helpers import (
    DOC1,
    DOC2,
    NOTES,
    P1,
    P2,
    Q1,
    Q2,
    QB,
    SEC1,
    SEC2,
    SESSION,
    FakeAsk,
    output,
    request,
    unit_json,
)

EXAMPLES = Path(__file__).resolve().parents[4] / "contracts" / "files" / "examples"


def test_t76_draft_key_is_the_contract_formula_of_the_first_anchor() -> None:
    # Red when: draft_key is any other formula: the v2 validator then refuses the whole result.
    out = draft_units(request(), FakeAsk(output(unit_json(anchors=[("D1.p3", Q1)]))))
    draft = out.drafts[0]
    assert draft.quote_hash == quote_hash(Q1)
    assert draft.draft_key == draft_key(SESSION, quote_hash(Q1))


def test_t76_first_anchor_does_not_depend_on_the_order_the_model_listed_them() -> None:
    # Red when: reordering the model's anchors changes the key (a redelivery would not match).
    a = output(unit_json(anchors=[("D1.p3", Q1), ("D1.p4", Q2)]))
    b = output(unit_json(anchors=[("D1.p4", Q2), ("D1.p3", Q1)]))
    key_a = draft_units(request(), FakeAsk(a)).drafts[0]
    key_b = draft_units(request(), FakeAsk(b)).drafts[0]
    assert key_a.draft_key == key_b.draft_key
    assert key_a.anchors == key_b.anchors


def test_us02b_ac3_every_anchor_quote_is_the_slice_of_its_source() -> None:
    # Red when: start/end are lost or point elsewhere than the quote.
    reply = output(unit_json(anchors=[("D1.p3", Q1), ("D1.p4", Q2), ("notes", NOTES[:30])]))
    drafts = draft_units(request(), FakeAsk(reply)).drafts
    pages = {(DOC1, 3): P1, (DOC1, 4): P2}
    for anchor in drafts[0].anchors:
        source = (
            NOTES if anchor.document_id is None else pages[(anchor.document_id, anchor.page or 0)]
        )
        assert source[anchor.start : anchor.end] == anchor.quote
        assert anchor.source == ("notes" if anchor.document_id is None else "document")


def test_us02b_ac4_three_sources_one_idea_one_draft_three_anchors() -> None:
    reply = output(unit_json(anchors=[("D1.p3", Q1), ("D2.p7", QB), ("notes", NOTES[:30])]))
    drafts = draft_units(request(), FakeAsk(reply)).drafts
    assert len(drafts) == 1 and len(drafts[0].anchors) == 3
    assert drafts[0].kind == "concept"


def test_t76_same_first_anchor_merges_anchors_and_sections() -> None:
    # Red when: the second unit's extra anchor or its section is lost in the merge.
    reply = output(
        unit_json("A", anchors=[("D1.p3", Q1)]),
        unit_json("B", anchors=[("D1.p3", Q1), ("D2.p7", QB)]),
    )
    drafts = draft_units(request(), FakeAsk(reply)).drafts
    assert len(drafts) == 1
    assert [a.document_id for a in drafts[0].anchors] == [DOC1, DOC2]
    assert drafts[0].section_ids == [SEC1, SEC2]
    assert drafts[0].draft_key == draft_key(SESSION, quote_hash(Q1))


def test_plan_t77_page_in_two_sections_draft_has_both() -> None:
    # PLAN T7.7 / T7.7a review: one page, two sections -> the draft carries both.
    req = DraftRequest(
        session_id=SESSION,
        scope=[
            ScopedDoc(
                document_id=DOC1,
                name="D",
                pages=[ScopedPage(page_no=3, text=P1, section_ids=[SEC1, SEC2])],
            )
        ],
    )
    drafts = draft_units(req, FakeAsk(output(unit_json(anchors=[("D1.p3", Q1)])))).drafts
    assert drafts[0].section_ids == [SEC1, SEC2]


def test_t76_submission_context_model_matches_the_contract_examples() -> None:
    body = (EXAMPLES / "submission-context.v1.json").read_text(encoding="utf-8")
    context = parse_context(body)
    assert isinstance(context, SubmissionContext)
    assert context.mentions[0].first_page == 40 and len(context.existing_units) == 1
    for bad in sorted(EXAMPLES.glob("submission-context.v1.invalid-*.json")):
        with pytest.raises(ValidationError):
            parse_context(bad.read_text(encoding="utf-8"))


def test_t76_submission_context_refuses_a_second_field_and_version_2() -> None:
    raw = json.loads((EXAMPLES / "submission-context.v1.json").read_text(encoding="utf-8"))
    for change in ({"version": 2}, {"extra": 1}):
        with pytest.raises(ValidationError):
            parse_context(json.dumps({**raw, **change}))
    assert uuid.UUID(raw["mentions"][0]["document_id"])
