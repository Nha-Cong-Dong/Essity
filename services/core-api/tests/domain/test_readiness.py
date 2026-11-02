"""T8.2a (US-14): question readiness, pure. Tests cite AC codes."""

import uuid

import pytest

from core_api.domain.readiness import (
    UNLINKED_LINE,
    Card,
    Ready,
    Section,
    Unlinked,
    Waiting,
    became_ready,
    display_line,
    readiness,
)


def sec(label: str, studied: bool = True, excluded: bool = False) -> Section:
    return Section(uuid.uuid4(), label, studied, excluded)


def index(*sections: Section) -> dict[uuid.UUID, Section]:
    return {s.id: s for s in sections}


def canon(s: Section) -> Card:
    return Card(s.id, True)


def draft(s: Section) -> Card:
    return Card(s.id, False)


A, B, C = sec("3.4"), sec("3.10"), sec("2.1", studied=False)
X = sec("9.9", studied=False, excluded=True)
ALL = index(A, B, C, X)


def test_ac4_studied_with_canonical_card_is_ready():
    assert readiness([A.id], ALL, [canon(A)]) == Ready()


def test_ac4_studied_without_canonical_card_waits():
    assert readiness([A.id], ALL, []) == Waiting((A,))
    assert readiness([A.id], ALL, [draft(A)]) == Waiting((A,))


def test_ac4_card_on_unstudied_section_waits():
    assert readiness([C.id], ALL, [canon(C)]) == Waiting((C,))


def test_ac4_multi_section_needs_every_section():
    assert readiness([A.id, B.id], ALL, [canon(A)]) == Waiting((B,))
    assert readiness([A.id, B.id], ALL, [canon(A), canon(B)]) == Ready()


def test_ac4_excluded_section_is_ignored():
    assert readiness([A.id, X.id], ALL, [canon(A)]) == Ready()


def test_ac4_only_excluded_sections_count_as_unlinked():
    assert readiness([X.id], ALL, []) == Unlinked()


def test_ac3_no_links_or_unknown_section_is_unlinked():
    assert readiness([], ALL, []) == Unlinked()
    assert readiness([uuid.uuid4()], ALL, []) == Unlinked()


def test_duplicate_links_and_cards_do_not_matter():
    assert readiness([A.id, A.id], ALL, [canon(A), canon(A)]) == Ready()


@pytest.mark.parametrize(
    ("studied", "canonical", "want_ready"),
    [(True, True, True), (True, False, False), (False, True, False), (False, False, False)],
)
def test_ac4_edge_table_single_section(studied: bool, canonical: bool, want_ready: bool):
    s = sec("1", studied=studied)
    cards = [Card(s.id, canonical)]
    assert isinstance(readiness([s.id], index(s), cards), Ready) is want_ready


def test_ac6_lines():
    assert display_line(Ready()) == "Sẵn sàng"
    assert display_line(Waiting((C,))) == "Chờ học: mục 2.1"
    assert display_line(Unlinked()) == UNLINKED_LINE


def test_ac6_several_sections_in_natural_order():
    state = readiness([B.id, C.id, A.id], ALL, [])
    assert display_line(state) == "Chờ học: mục 2.1, 3.4, 3.10"


def test_ac6_unicode_label_kept():
    s = sec("Chương Ⅱ — Đại số")
    assert display_line(readiness([s.id], index(s), [])) == "Chờ học: mục Chương Ⅱ — Đại số"


def test_ac4_saving_last_needed_card_flips_to_ready():
    assert became_ready([A.id, B.id], ALL, [canon(A)], canon(B))


def test_ac4_not_ready_yet_or_already_ready_is_no_flip():
    assert not became_ready([A.id, B.id], ALL, [], canon(A))
    assert not became_ready([A.id], ALL, [canon(A)], canon(A))
    assert not became_ready([A.id], ALL, [], draft(A))


# T8.2: outline numbers shown in "Chờ học: mục X".
def test_outline_numbers_follow_the_tree_and_sibling_order_us14_ac4():
    from core_api.domain.readiness import OutlineNode, outline_numbers

    a, b, c, d = (uuid.UUID(int=i) for i in (1, 2, 3, 4))
    nodes = [
        OutlineNode(c, a, 1),  # second child of a
        OutlineNode(a, None, 0),
        OutlineNode(b, a, 0),  # first child of a
        OutlineNode(d, None, 1),
    ]
    assert outline_numbers(nodes) == {a: "1", b: "1.1", c: "1.2", d: "2"}
