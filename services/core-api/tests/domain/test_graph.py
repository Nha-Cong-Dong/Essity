"""T9.9a (US-19): graph edge rules, pure. Tests cite AC codes or the PLAN T9.9 rule."""

import math
import uuid

from core_api.domain.graph import (
    CARD_CARD_KINDS,
    Anchor,
    CardChange,
    Edge,
    EdgeKind,
    EdgeProposal,
    EdgeStatus,
    Evidence,
    Rejection,
    deactivate_edges,
    edge_key,
    merge_proposals,
    prerequisite_leaves,
    proposal_batches,
    validate_edge,
)

SUBJ, OTHER = uuid.uuid4(), uuid.uuid4()
A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ANCHORS = {
    A: Anchor(A, SUBJ, "Hàm số liên tục tại một điểm\nkhi giới hạn bằng giá trị hàm."),
    B: Anchor(B, SUBJ, "Đạo hàm cần hàm số liên tục."),
    C: Anchor(C, OTHER, "Đạo hàm cần hàm số liên tục."),
}


def prop(
    kind: EdgeKind = EdgeKind.PREREQUISITE,
    s: uuid.UUID = B,
    t: uuid.UUID = A,
    ev: tuple[Evidence, ...] | None = None,
) -> EdgeProposal:
    if ev is None:
        ev = (Evidence(B, "cần hàm số liên tục"),)
    return EdgeProposal(kind, s, t, ev)


def test_ac1_kinds_enumerated_without_generic_related():
    assert {k.value for k in EdgeKind} == {
        "card_section",
        "question_card",
        "prerequisite",
        "part_of",
        "example_of",
        "contrast",
        "applies_to",
    }
    assert len(CARD_CARD_KINDS) == 5


def test_ac2_valid_proposal_accepted():
    assert validate_edge(prop(), ANCHORS).ok


def test_ac2_quote_matches_after_nfc_and_whitespace():
    decomposed = "Hàm số liên tục".replace("à", "à")  # NFD input
    assert validate_edge(prop(ev=(Evidence(A, decomposed),)), ANCHORS).ok
    spans_newline = (Evidence(A, "liên tục tại một điểm khi   giới hạn"),)
    assert validate_edge(prop(ev=spans_newline), ANCHORS).ok


def test_ac2_diacritics_must_match():
    v = validate_edge(prop(ev=(Evidence(B, "can ham so lien tuc"),)), ANCHORS)
    assert v.reason is Rejection.EVIDENCE_NOT_FOUND


def test_ac2_no_evidence_rejected():
    assert validate_edge(prop(ev=()), ANCHORS).reason is Rejection.NO_EVIDENCE


def test_ac2_invented_or_empty_quote_rejected():
    for quote in ("không có trong neo", "  "):
        v = validate_edge(prop(ev=(Evidence(B, quote),)), ANCHORS)
        assert v.reason is Rejection.EVIDENCE_NOT_FOUND


def test_ac2_one_bad_quote_rejects_all():
    ev = (Evidence(B, "cần hàm số liên tục"), Evidence(A, "bịa"))
    assert not validate_edge(prop(ev=ev), ANCHORS).ok


def test_ac2_quote_from_unrelated_card_rejected():
    ev = (Evidence(C, "Đạo hàm cần"),)
    assert validate_edge(prop(ev=ev), ANCHORS).reason is Rejection.EVIDENCE_NOT_FOUND


def test_ac2_cross_subject_rejected():
    v = validate_edge(prop(s=C, t=A, ev=(Evidence(C, "Đạo hàm cần"),)), ANCHORS)
    assert v.reason is Rejection.CROSS_SUBJECT


def test_ac2_self_loop_and_unknown_card_rejected():
    assert validate_edge(prop(s=A, t=A), ANCHORS).reason is Rejection.SELF_LOOP
    assert validate_edge(prop(t=uuid.uuid4()), ANCHORS).reason is Rejection.UNKNOWN_CARD


def test_ac2_system_does_not_propose_section_or_question_edges():
    for kind in (EdgeKind.CARD_SECTION, EdgeKind.QUESTION_CARD):
        assert validate_edge(prop(kind=kind), ANCHORS).reason is Rejection.WRONG_KIND


def test_resent_unit_saved_adds_no_duplicate_edge():
    first = [prop(), prop(kind=EdgeKind.PART_OF)]
    stored = {edge_key(p.kind, p.source_id, p.target_id) for p in first}
    assert merge_proposals(stored, first) == []
    assert merge_proposals([], first + first) == first


def test_contrast_is_symmetric_but_prerequisite_is_not():
    reversed_contrast = prop(EdgeKind.CONTRAST, B, A)
    assert merge_proposals([edge_key(EdgeKind.CONTRAST, A, B)], [reversed_contrast]) == []
    assert len(merge_proposals([edge_key(EdgeKind.PREREQUISITE, A, B)], [prop()])) == 1


def test_card_change_turns_touching_edges_inactive():
    on_a = Edge(EdgeKind.PREREQUISITE, B, A)
    on_c = Edge(EdgeKind.PART_OF, C, uuid.uuid4())
    for change in CardChange:
        out = deactivate_edges([on_a, on_c], change, [A])
        assert [e.status for e in out] == [EdgeStatus.INACTIVE, EdgeStatus.ACTIVE]
    assert on_a.status is EdgeStatus.ACTIVE  # input untouched


def test_proposal_calls_are_linear_in_cards():
    for n in (0, 1, 10, 11, 100, 250):
        cards = [uuid.uuid4() for _ in range(n)]
        batches = proposal_batches(cards)
        assert len(batches) == math.ceil(n / 10)
        assert [c for b in batches for c in b] == cards


def test_us15_ac2_prerequisite_leaves_for_suggest():
    la, lb = uuid.uuid4(), uuid.uuid4()
    edges = [
        Edge(EdgeKind.PREREQUISITE, B, A),
        Edge(EdgeKind.PREREQUISITE, B, A),  # duplicate collapses
        Edge(EdgeKind.PART_OF, A, B),  # other kind ignored
        Edge(EdgeKind.PREREQUISITE, A, C, EdgeStatus.INACTIVE),  # inactive ignored
    ]
    assert prerequisite_leaves(edges, {A: la, B: lb, C: lb}) == {lb: (la,)}
    same_leaf = [Edge(EdgeKind.PREREQUISITE, B, A)]
    assert prerequisite_leaves(same_leaf, {A: la, B: la}) == {}
    assert prerequisite_leaves(same_leaf, {A: la}) == {}  # unmapped card
