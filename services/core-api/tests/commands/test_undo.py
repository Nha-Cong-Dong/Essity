"""T9.2d: undo a command by its id (US-18 AC5; ADR-0030): newest first, refused when anything it
wrote has moved on, nothing deleted."""

import uuid
from datetime import UTC, date, datetime

import pytest
from cmd_world import CmdWorld
from sqlalchemy import select

from core_api.db.models import CommandLog, KnowledgeUnit, PracticeRemovalLog, User
from core_api.domain.commands.registry import CommandRejected
from core_api.repositories.command_log import CommandLogRepository
from core_api.repositories.practice_removal import PracticeRemovalRepository
from core_api.repositories.study_filter import StudyFilterRepository
from core_api.services import practice
from core_api.services.outline import OutlineService


def exclude(section: object) -> list[dict[str, object]]:
    return [{"kind": "section_exclude", "sections": [str(section.id)]}]  # type: ignore[attr-defined]


def undo_code(cw: CmdWorld, cid: uuid.UUID) -> CommandRejected:
    with pytest.raises(CommandRejected) as caught:
        cw.service.undo(cid)
    return caught.value


def test_ac5_undo_restores_and_marks_undone(cw: CmdWorld) -> None:  # AC5
    cid = uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=cid)
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is True
    out = cw.service.undo(cid)
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is False and cw.leaf1.source != "user"
    row = CommandLogRepository(cw.db, cw.user.id).by_command_id(cid)
    assert row and row.status == "undone" and row.undone_at is not None
    assert row.undo_revs_json == {f"doc_section:{cw.leaf1.id}": cw.leaf1.version}
    assert out.status == "undone" and not out.replayed and out.affected == 1
    assert out.diff[0]["verb"] == "reverted"


def test_ac5_undo_same_command_twice_does_not_undo_older(cw: CmdWorld) -> None:  # AC5
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=c1)
    cw.run(exclude(cw.leaf2), command_id=c2)
    first = cw.service.undo(c2)
    again = cw.service.undo(c2)
    cw.db.refresh(cw.leaf1)
    cw.db.refresh(cw.leaf2)
    assert again.replayed and again.diff == first.diff
    assert cw.leaf1.excluded is True and cw.leaf2.excluded is False


def test_ac5_undo_newest_first_only(cw: CmdWorld) -> None:  # AC5
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=c1)
    cw.run(exclude(cw.leaf2), command_id=c2)
    assert undo_code(cw, c1).code == "not_latest"
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is True
    cw.service.undo(c2)
    cw.service.undo(c1)  # now it is the newest open one
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is False


def test_ac5_newest_open_is_per_session(cw: CmdWorld) -> None:  # AC5
    other, c1, c2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=c1)
    cw.run(exclude(cw.leaf2), command_id=c2, session_id=other)
    cw.service.undo(c1)  # c2 is in another session: it does not block
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is False


def test_ac5_undo_refused_when_manually_edited_after(cw: CmdWorld) -> None:  # AC5
    cid = uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=cid)
    OutlineService(cw.db, cw.user.id).edit_section(cw.leaf1.id, excluded=False)
    error = undo_code(cw, cid)
    cw.db.refresh(cw.leaf1)
    row = CommandLogRepository(cw.db, cw.user.id).by_command_id(cid)
    assert error.code == "changed_after" and str(cw.leaf1.id) in error.detail
    assert cw.leaf1.excluded is False  # the manual edit stays
    assert row and row.status == "applied" and row.undo_revs_json is None


def test_ac5_refusal_rolls_back_the_objects_written_before(cw: CmdWorld) -> None:  # AC5
    cid = uuid.uuid4()
    q = cw.questions[0]
    cw.run(
        [
            *exclude(cw.leaf1),
            {"kind": "question_set_answer", "question": str(q.id), "text": "đáp"},
        ],
        command_id=cid,
    )
    cw.db.refresh(q)
    q.answer_text = "sửa tay"  # the trigger raises the version of the question
    cw.db.flush()
    assert undo_code(cw, cid).code == "changed_after"
    cw.db.refresh(cw.leaf1)
    cw.db.refresh(q)
    assert cw.leaf1.excluded is True and q.answer_text == "sửa tay"


def test_ac5_undo_other_users_command_404(cw: CmdWorld, two_users: tuple[User, User]) -> None:
    cid = uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=cid)
    bob = CmdWorld(cw.db, two_users[1])
    for wanted in (cid, uuid.uuid4()):
        with pytest.raises(CommandRejected) as caught:
            bob.service.undo(wanted)
        assert caught.value.code == "not_owned"
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is True


def test_ac5_undo_after_a_later_command_was_undone(cw: CmdWorld) -> None:  # AC5, undo_revs
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    q = str(cw.questions[0].id)
    cw.run([{"kind": "question_set_answer", "question": q, "text": "một"}], command_id=c1)
    cw.run([{"kind": "question_set_answer", "question": q, "text": "hai"}], command_id=c2)
    cw.service.undo(c2)
    cw.service.undo(c1)  # c2 left a newer rev: c1 looks at the one c2 left, not its own
    cw.db.refresh(cw.questions[0])
    assert cw.questions[0].answer_text is None


def test_ac5_undo_card_edit_merge_add_discard(cw: CmdWorld) -> None:  # AC5
    c0, c1, c2 = (str(c.id) for c in cw.cards)
    before = {c.id: (c.summary, c.status) for c in cw.cards}
    ids = [uuid.uuid4() for _ in range(4)]
    cw.run([{"kind": "card_edit", "card": c0, "text": "mới"}], command_id=ids[0])
    cw.run([{"kind": "card_merge", "cards": [c1, c2]}], command_id=ids[1])
    add = cw.run(
        [{"kind": "card_add", "text": "Thẻ mới\nchi tiết", "section": str(cw.leaf1.id)}],
        command_id=ids[2],
    )
    cw.run([{"kind": "card_discard_draft", "card": c0}], command_id=ids[3])
    for cid in reversed(ids):
        cw.service.undo(cid)
    for card in cw.cards:
        cw.db.refresh(card)
        assert (card.summary, card.status) == before[card.id]
    made = cw.db.get(KnowledgeUnit, uuid.UUID(add.diff[0]["id"]))
    assert made is not None and made.status == "retired" and made.retired_at is not None


def test_ac5_undo_merge_then_merge_again(cw: CmdWorld) -> None:  # AC5
    c1, c2 = (str(c.id) for c in cw.cards[1:])
    first = uuid.uuid4()
    cw.run([{"kind": "card_merge", "cards": [c1, c2]}], command_id=first)
    cw.service.undo(first)
    cw.run([{"kind": "card_merge", "cards": [c1, c2]}])  # no lineage left to clash with


def test_ac5_undo_card_split_discards_the_parts(cw: CmdWorld) -> None:  # AC5
    cid = uuid.uuid4()
    out = cw.run([{"kind": "card_split", "card": str(cw.cards[0].id), "parts": 2}], command_id=cid)
    made = [d for d in out.diff if d["verb"] == "added"]
    cw.service.undo(cid)
    cw.db.refresh(cw.cards[0])
    assert cw.cards[0].summary.startswith("Nội dung 0")
    unit = cw.db.get(KnowledgeUnit, uuid.UUID(made[0]["id"]))
    assert unit is not None and unit.status == "retired"


def test_ac5_undo_card_manually_edited_after_is_refused(cw: CmdWorld) -> None:  # AC5
    cid = uuid.uuid4()
    cw.run([{"kind": "card_edit", "card": str(cw.cards[0].id), "text": "mới"}], command_id=cid)
    cw.db.refresh(cw.cards[0])
    cw.cards[0].summary = "tay"
    cw.cards[0].version += 1
    cw.db.flush()
    error = undo_code(cw, cid)
    assert error.code == "changed_after" and "unit" in error.detail


def test_ac5_undo_question_type_and_answer(cw: CmdWorld) -> None:  # AC5
    q = cw.questions[1]
    cid = uuid.uuid4()
    cw.run(
        [
            {"kind": "question_set_type", "question": str(q.id), "question_type": str(cw.qtype.id)},
            {"kind": "question_set_answer", "question": str(q.id), "text": "đáp"},
        ],
        command_id=cid,
    )
    cw.service.undo(cid)
    cw.db.refresh(q)
    assert q.type_id is None and q.answer_text is None


def test_f2_undo_remove_writes_readded(cw: CmdWorld) -> None:  # F2, AC5
    q, cid = cw.questions[0], uuid.uuid4()
    cw.run([{"kind": "question_remove_from_practice", "question": str(q.id)}], command_id=cid)
    repo = PracticeRemovalRepository(cw.db, cw.user.id)
    assert not repo.in_practice(q.id)
    cw.service.undo(cid)
    assert repo.in_practice(q.id)
    actions = cw.db.scalars(
        select(PracticeRemovalLog.action)
        .where(PracticeRemovalLog.question_id == q.id)
        .order_by(PracticeRemovalLog.id)
    ).all()
    assert list(actions) == ["removed", "readded"]
    row = CommandLogRepository(cw.db, cw.user.id).by_command_id(cid)
    assert row and row.undo_revs_json == {f"practice_removal:{q.id}": repo.rev(q.id)}


def test_f2_in_practice_rev_detects_manual_readd(cw: CmdWorld) -> None:  # F2, AC5
    q, cid = cw.questions[0], uuid.uuid4()
    cw.run([{"kind": "question_remove_from_practice", "question": str(q.id)}], command_id=cid)
    practice.readd(cw.db, cw.user.id, q.id)
    practice.remove(cw.db, cw.user.id, q.id, at=datetime.now(UTC))
    assert undo_code(cw, cid).code == "changed_after"
    assert not PracticeRemovalRepository(cw.db, cw.user.id).in_practice(q.id)


def test_study_filter_undo_keeps_row_bumps_rev(cw: CmdWorld) -> None:  # ABA
    cid = uuid.uuid4()
    until = date(2030, 1, 1).isoformat()
    cw.run(
        [{"kind": "suggest_only_subject", "subject": str(cw.subject.id), "until": until}],
        command_id=cid,
    )
    repo = StudyFilterRepository(cw.db, cw.user.id)
    assert repo.state(cw.subject.id).rev == 1
    cw.service.undo(cid)
    state = repo.state(cw.subject.id)
    assert (state.mode, state.until, state.rev) == (None, None, 2)


def test_study_filter_undo_restores_the_older_filter(cw: CmdWorld) -> None:
    sid, until = str(cw.subject.id), date(2030, 1, 1).isoformat()
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    cw.run([{"kind": "suggest_only_subject", "subject": sid, "until": until}], command_id=c1)
    cw.run(
        [{"kind": "suggest_defer_subject", "subject": sid, "until": "2031-02-03"}], command_id=c2
    )
    cw.service.undo(c2)
    state = StudyFilterRepository(cw.db, cw.user.id).state(cw.subject.id)
    assert (state.mode, state.until) == ("only", date(2030, 1, 1)) and state.rev == 3


def test_review_y1_filter_mode_and_until_go_together(cw: CmdWorld) -> None:  # T9.2b Y1
    repo = StudyFilterRepository(cw.db, cw.user.id)
    with pytest.raises(ValueError):
        repo.set(cw.subject.id, "only", None)
    with pytest.raises(ValueError):
        repo.set(cw.subject.id, None, date(2030, 1, 1))
    assert repo.state(cw.subject.id).rev == 0


def test_op_pair_that_cancels_undoes_to_a_clean_noop(cw: CmdWorld) -> None:  # T9.2c note
    cid, pid = uuid.uuid4(), str(cw.leaf1.id)
    cw.run(
        [
            {"kind": "section_mark", "sections": [pid], "studied": True},
            {"kind": "section_mark", "sections": [pid], "studied": False},
        ],
        command_id=cid,
    )
    cw.db.refresh(cw.leaf1)
    version = cw.leaf1.version
    cw.service.undo(cid)
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.studied_weight == 0 and cw.leaf1.version == version


def test_mark_undone_refuses_a_command_that_is_not_the_newest(cw: CmdWorld) -> None:  # Y3
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=c1)
    cw.run(exclude(cw.leaf2), command_id=c2)
    repo = CommandLogRepository(cw.db, cw.user.id)
    assert repo.mark_undone(c1) is None
    assert repo.mark_undone(c2) is not None
    assert repo.mark_undone(c1) is not None


def test_undo_does_not_touch_the_log_beyond_one_flip(cw: CmdWorld) -> None:
    cid = uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=cid)
    before = cw.db.scalar(select(CommandLog.inverse_json).where(CommandLog.command_id == cid))
    cw.service.undo(cid)
    after = cw.db.scalar(select(CommandLog.inverse_json).where(CommandLog.command_id == cid))
    assert before == after
