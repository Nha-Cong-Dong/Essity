"""QA2 N1: the learner's declared pages make sections "studied" (US-13 AC6), whichever section
the AI hung the card on."""

from cmd_world import CmdWorld
from core_api.domain.unit_review import NewRange, UnitReviewService


def test_declared_pages_credit_the_leaves_they_cover(cw: CmdWorld) -> None:
    cw.leaf1.first_page, cw.leaf1.last_page = 7, 7  # 1.1.2
    cw.leaf2.first_page, cw.leaf2.last_page = 7, 8  # 1.1.3, same page but longer
    cw.db.flush()
    UnitReviewService(cw.db, cw.user.id).credit_ranges([NewRange(cw.document.id, 7, 7)])
    cw.db.refresh(cw.leaf1)
    cw.db.refresh(cw.leaf2)
    assert cw.leaf1.studied_weight == 2  # fully covered
    assert cw.leaf2.studied_weight == 1  # half the pages, half the weight
    cw.db.refresh(cw.parent)
    assert cw.parent.studied_weight == 0  # only leaves carry progress


def test_crediting_never_lowers_and_ignores_other_pages(cw: CmdWorld) -> None:
    cw.leaf1.first_page, cw.leaf1.last_page = 1, 2
    cw.leaf1.studied_weight = 2
    cw.leaf2.first_page, cw.leaf2.last_page = 3, 4
    cw.db.flush()
    UnitReviewService(cw.db, cw.user.id).credit_ranges([NewRange(cw.document.id, 1, 1)])
    cw.db.refresh(cw.leaf1)
    cw.db.refresh(cw.leaf2)
    assert cw.leaf1.studied_weight == 2 and cw.leaf2.studied_weight == 0
