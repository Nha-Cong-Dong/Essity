"""T9.2d tester: edge cases of undo (US-18 AC5) not covered by test_undo.py: several undos in a
row on one object, an object gone since, two users with one command id, two ops on one field,
undo_revs written once, practice removal undone twice."""

import uuid

import pytest
from cmd_world import CmdWorld
from sqlalchemy import select

from core_api.db.models import CommandLog, PracticeRemovalLog, UnitSection, User
from core_api.domain.commands.registry import CommandRejected
from core_api.domain.unit_review import UnitChangedElsewhere, UnitReviewService
from core_api.repositories.command_log import CommandLogRepository
from core_api.repositories.practice_removal import PracticeRemovalRepository


def answer(question: object, text: str) -> dict[str, object]:
    return {"kind": "question_set_answer", "question": str(question.id), "text": text}  # type: ignore[attr-defined]


def test_ac5_undo_three_commands_on_one_question_newest_first(cw: CmdWorld) -> None:  # AC5
    # Red when: the undo of C1 takes the rev left by C3's undo (the first one) instead of the rev
    # left by C2's undo (the last one) and answers a false changed_after.
    q = cw.questions[0]
    ids = [uuid.uuid4() for _ in range(3)]
    for cid, text in zip(ids, ("một", "hai", "ba"), strict=True):
        cw.run([answer(q, text)], command_id=cid)
    for cid in reversed(ids):
        cw.service.undo(cid)
    cw.db.refresh(q)
    assert q.answer_text is None


def test_ac5_undo_three_commands_then_manual_edit_refused(cw: CmdWorld) -> None:  # AC5
    # Red when: a manual edit after the later undos is not seen (expected rev taken from a later
    # command, not compared to the row).
    q = cw.questions[0]
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    cw.run([answer(q, "một")], command_id=c1)
    cw.run([answer(q, "hai")], command_id=c2)
    cw.service.undo(c2)
    cw.db.refresh(q)
    q.answer_text = "tay"
    cw.db.flush()
    with pytest.raises(CommandRejected) as caught:
        cw.service.undo(c1)
    assert caught.value.code == "changed_after" and str(q.id) in caught.value.detail
    cw.db.refresh(q)
    assert q.answer_text == "tay"


def test_ac5_undo_when_section_is_gone_is_refused(cw: CmdWorld) -> None:  # AC5
    # Red when: a row deleted since the apply is treated as unchanged (None == expected) or the
    # undo crashes instead of answering changed_after with the object.
    cid = uuid.uuid4()
    cw.run(
        [{"kind": "section_exclude", "sections": [str(cw.leaf2.id)]}, answer(cw.questions[0], "x")],
        command_id=cid,
    )
    gone = cw.leaf2.id
    cw.db.delete(cw.leaf2)
    cw.db.flush()
    with pytest.raises(CommandRejected) as caught:
        cw.service.undo(cid)
    assert caught.value.code == "changed_after" and str(gone) in caught.value.detail
    cw.db.refresh(cw.questions[0])
    row = CommandLogRepository(cw.db, cw.user.id).by_command_id(cid)
    assert cw.questions[0].answer_text == "x"  # nothing written
    assert row is not None and row.status == "applied"


def test_ac5_two_users_same_command_id_undo_only_their_own(
    cw: CmdWorld, two_users: tuple[User, User]
) -> None:  # AC5, isolation
    # Red when: undo looks the command up without user_id (B's undo reverses A's command, or
    # A's undo flips B's log row).
    cid = uuid.uuid4()
    bob = CmdWorld(cw.db, two_users[1])
    cw.run([{"kind": "section_exclude", "sections": [str(cw.leaf1.id)]}], command_id=cid)
    bob.run([{"kind": "section_exclude", "sections": [str(bob.leaf2.id)]}], command_id=cid)
    bob.service.undo(cid)
    for s in (cw.leaf1, bob.leaf2):
        cw.db.refresh(s)
    assert cw.leaf1.excluded is True and bob.leaf2.excluded is False
    rows = cw.db.scalars(select(CommandLog).where(CommandLog.command_id == cid)).all()
    assert sorted((r.user_id == bob.user.id, r.status) for r in rows) == [
        (False, "applied"),
        (True, "undone"),
    ]
    cw.service.undo(cid)
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is False


def test_ac5_two_ops_on_one_field_undo_to_the_first_value(cw: CmdWorld) -> None:  # AC5
    # Red when: the before-image of the second op on the same row overwrites the first one
    # (undo restores "một", the middle value, instead of the value before the command).
    q, cid = cw.questions[0], uuid.uuid4()
    cw.run([answer(q, "một"), answer(q, "hai")], command_id=cid)
    cw.db.refresh(q)
    assert q.answer_text == "hai"
    cw.service.undo(cid)
    cw.db.refresh(q)
    assert q.answer_text is None


def test_ac5_card_edit_then_merge_in_one_command_undoes_both(cw: CmdWorld) -> None:  # AC5
    # Red when: merging the before-images drops the first summary or the merge's extra fields.
    c1, c2 = cw.cards[1], cw.cards[2]
    before = {c.id: (c.summary, c.status) for c in (c1, c2)}
    cid = uuid.uuid4()
    cw.run(
        [
            {"kind": "card_edit", "card": str(c1.id), "text": "sửa"},
            {"kind": "card_merge", "cards": [str(c1.id), str(c2.id)]},
        ],
        command_id=cid,
    )
    cw.service.undo(cid)
    for card in (c1, c2):
        cw.db.refresh(card)
        assert (card.summary, card.status) == before[card.id]


def test_ac5_undo_revs_written_once(cw: CmdWorld) -> None:  # AC5, undo_revs
    # Red when: a replayed undo (or mark_undone again) rewrites undo_revs_json or undone_at.
    cid = uuid.uuid4()
    cw.run([answer(cw.questions[0], "một")], command_id=cid)
    cw.service.undo(cid)
    repo = CommandLogRepository(cw.db, cw.user.id)
    row = repo.by_command_id(cid)
    assert row is not None and row.undo_revs_json
    first = (dict(row.undo_revs_json), row.undone_at)
    assert repo.mark_undone(cid, undo_revs={"x": 1}) is None
    again = cw.service.undo(cid)
    cw.db.refresh(row)
    assert again.replayed and (row.undo_revs_json, row.undone_at) == first


def test_f2_practice_removal_removed_undone_twice(cw: CmdWorld) -> None:  # F2, AC5
    # Red when: the second undo checks the practice rev against the first command's id (stale
    # max log id) or readds without a new event.
    q = cw.questions[0]
    repo = PracticeRemovalRepository(cw.db, cw.user.id)
    for _ in range(2):
        cid = uuid.uuid4()
        cw.run([{"kind": "question_remove_from_practice", "question": str(q.id)}], command_id=cid)
        assert not repo.in_practice(q.id)
        cw.service.undo(cid)
        assert repo.in_practice(q.id)
    actions = cw.db.scalars(
        select(PracticeRemovalLog.action)
        .where(PracticeRemovalLog.question_id == q.id)
        .order_by(PracticeRemovalLog.id)
    ).all()
    assert list(actions) == ["removed", "readded", "removed", "readded"]


def test_f2_practice_removal_then_answer_undo_in_turn(cw: CmdWorld) -> None:  # F2, AC5
    # Red when: undoing the answer on the question (same row lock, other table) trips the
    # practice check of the older command.
    q = cw.questions[0]
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    cw.run([{"kind": "question_remove_from_practice", "question": str(q.id)}], command_id=c1)
    cw.run([answer(q, "đáp")], command_id=c2)
    cw.service.undo(c2)
    cw.service.undo(c1)
    cw.db.refresh(q)
    assert q.answer_text is None and PracticeRemovalRepository(cw.db, cw.user.id).in_practice(q.id)


def test_ac5_undone_card_gets_a_new_version(cw: CmdWorld) -> None:  # AC5, rev
    # Red when: the undo writes the card back without raising its version, so a screen that
    # loaded the card before the undo saves over it.
    card, cid = cw.cards[0], uuid.uuid4()
    cw.run([{"kind": "card_edit", "card": str(card.id), "text": "mới"}], command_id=cid)
    cw.db.refresh(card)
    seen = card.version
    cw.service.undo(cid)
    cw.db.refresh(card)
    assert card.version > seen
    with pytest.raises(UnitChangedElsewhere):
        UnitReviewService(cw.db, cw.user.id).edit(card.id, seen, content="màn cũ")


def test_ac5_newer_command_landing_during_undo_is_not_latest(
    cw: CmdWorld, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC5, review Y3
    # Red when: a newer command that slips past the first `not_latest` check is let through by
    # mark_undone, or the writes of the refused undo are not rolled back (no savepoint).
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    cw.run(exclude_ops(cw.leaf1), command_id=c1)
    cw.run(exclude_ops(cw.leaf2), command_id=c2)
    log = cw.service.log
    stale = log.by_command_id(c1)

    def not_seen_yet(_sid: uuid.UUID) -> CommandLog | None:  # the race: c2 not yet seen
        return stale

    monkeypatch.setattr(log, "latest_open", not_seen_yet)
    with pytest.raises(CommandRejected) as caught:
        cw.service.undo(c1)
    assert caught.value.code == "not_latest"
    cw.db.refresh(cw.leaf1)
    row = CommandLogRepository(cw.db, cw.user.id).by_command_id(c1)
    assert cw.leaf1.excluded is True and row is not None and row.status == "applied"


def test_ac5_other_users_command_in_same_screen_session_does_not_block(
    cw: CmdWorld, two_users: tuple[User, User]
) -> None:  # AC5, isolation
    # Red when: "newest of the session" counts another user's command with the same screen
    # session id (the client picks that id): B could block A's undo.
    bob = CmdWorld(cw.db, two_users[1])
    cid = uuid.uuid4()
    cw.run(exclude_ops(cw.leaf1), command_id=cid)
    bob.run(exclude_ops(bob.leaf1))  # same SESSION id, later
    cw.service.undo(cid)
    cw.db.refresh(cw.leaf1)
    cw.db.refresh(bob.leaf1)
    assert cw.leaf1.excluded is False and bob.leaf1.excluded is True


def test_ac5_undo_merge_gives_back_the_sections_taken_in(cw: CmdWorld) -> None:  # AC5
    # Red when: undoing a merge leaves on the kept card the sections of the card merged away.
    c1, c2 = cw.cards[1], cw.cards[2]
    for card, section in ((c1, cw.leaf1), (c2, cw.leaf2)):
        cw.db.add(
            UnitSection(
                user_id=cw.user.id, subject_id=cw.subject.id, unit_id=card.id, section_id=section.id
            )
        )
    cw.db.flush()
    cid = uuid.uuid4()
    cw.run([{"kind": "card_merge", "cards": [str(c1.id), str(c2.id)]}], command_id=cid)

    def sections_of(unit_id: uuid.UUID) -> set[uuid.UUID]:
        return set(
            cw.db.scalars(select(UnitSection.section_id).where(UnitSection.unit_id == unit_id))
        )

    kept = c1.id if sections_of(c1.id) == {cw.leaf1.id, cw.leaf2.id} else c2.id
    assert sections_of(kept) == {cw.leaf1.id, cw.leaf2.id}
    cw.service.undo(cid)
    assert sections_of(c1.id) == {cw.leaf1.id} and sections_of(c2.id) == {cw.leaf2.id}


def exclude_ops(section: object) -> list[dict[str, object]]:
    return [{"kind": "section_exclude", "sections": [str(section.id)]}]  # type: ignore[attr-defined]
