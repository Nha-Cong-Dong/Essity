"""Pure draft-review rules (T7.8; US-02b AC6-AC9, AC12)."""

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core_api.domain import unit_review as ur

S = uuid.UUID(int=1)
T0 = datetime(2026, 11, 1, tzinfo=UTC)


def card(n: int, **kw: object) -> ur.DraftCard:
    base: dict[str, object] = dict(
        id=uuid.UUID(int=100 + n), session_id=S, title=f"t{n}", content=f"c{n}", kind="concept",
        status="draft", version=1, created_at=T0 + timedelta(minutes=n),
        anchor_ids=(uuid.UUID(int=n),), section_ids=(),
    )  # fmt: skip
    base.update(kw)
    return ur.DraftCard(**base)  # type: ignore[arg-type]


def test_ac7_stale_version_raises_with_the_message() -> None:
    ur.check_version(3, 3)
    with pytest.raises(ur.UnitChangedElsewhere) as e:
        ur.check_version(4, 3)
    assert e.value.message == "thẻ đã đổi ở nơi khác"


def test_ac6_merge_keeps_oldest_joins_in_order_no_llm() -> None:
    kept, rest = ur.merge([card(3), card(1), card(2)])
    assert kept.id == card(1).id and kept.content == "c1\n\nc2\n\nc3"
    assert [c.id for c in rest] == [card(2).id, card(3).id]
    assert kept.anchor_ids == (uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3))
    assert ur.merge([card(2), card(1)]) == ur.merge([card(1), card(2)])


def test_ac6_merge_and_split_refuse_canonical_or_other_sessions() -> None:
    with pytest.raises(ur.NotADraft):
        ur.merge([card(1), card(2, status="canonical")])
    with pytest.raises(ur.NotADraft):
        ur.merge([card(1), card(2, session_id=uuid.UUID(int=9))])
    with pytest.raises(ur.NotADraft):
        ur.split(card(1, status="canonical"), [])


def test_ac6_split_checks_anchors() -> None:
    c = card(1, anchor_ids=(uuid.UUID(int=5), uuid.UUID(int=6)))
    ok = [ur.SplitPart("a", "x", (uuid.UUID(int=5),)), ur.SplitPart("b", "y", (uuid.UUID(int=6),))]
    assert ur.split(c, ok) == ok
    with pytest.raises(ValueError):
        ur.split(c, ok[:1])
    with pytest.raises(ValueError):
        ur.split(c, [ok[0], ur.SplitPart("b", "y", (uuid.UUID(int=5),))])
    with pytest.raises(ValueError):
        ur.split(c, [ok[0], ur.SplitPart("b", "y", (uuid.UUID(int=77),))])


def test_ac8_undo_window_is_seven_days() -> None:
    assert ur.can_undo(T0, T0 + timedelta(days=7))
    assert not ur.can_undo(T0, T0 + timedelta(days=7, seconds=1))
    with pytest.raises(ur.UndoExpired):
        ur.require_undo(T0, T0 + timedelta(days=8))


@pytest.mark.parametrize(("hh", "mm", "day"), [(3, 59, 31), (4, 0, 1)])
def test_ac12_saved_learning_day_boundary(hh: int, mm: int, day: int) -> None:
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    now = datetime(2026, 11, 1, hh, mm, tzinfo=tz)
    d = ur.saved_learning_day(now, tz, 4)
    assert d.day == day
    assert not ur.in_review(d, d)
    assert ur.in_review(d, d + timedelta(days=1))
