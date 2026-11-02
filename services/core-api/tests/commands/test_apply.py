"""T9.2c: apply a command in one transaction (US-18 AC4, AC6, AC8, AC9; ADR-0030)."""

import logging
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from cmd_world import SESSION, CmdWorld, Parser
from core_api.db.models import CommandLog, KnowledgeUnit, PracticeRemovalLog, User
from core_api.domain.commands.registry import CommandRejected
from core_api.repositories.command_log import CommandLogRepository
from core_api.repositories.practice_removal import PracticeRemovalRepository
from core_api.repositories.study_filter import StudyFilterRepository
from core_api.services import practice
from core_api.services.command_codec import APPLICABLE_KINDS
from core_api.services.commands import CommandIdReused, CommandRequest


def rows(cw: CmdWorld) -> int:
    return cw.db.scalar(select(func.count()).select_from(CommandLog)) or 0


def exclude(section: object) -> list[dict[str, object]]:
    return [{"kind": "section_exclude", "sections": [str(section.id)]}]  # type: ignore[attr-defined]


def test_ac4_same_command_id_applies_once(cw: CmdWorld) -> None:  # AC4
    cid = uuid.uuid4()
    first = cw.run(exclude(cw.leaf1), command_id=cid)
    again = cw.run(exclude(cw.leaf1), command_id=cid)
    assert rows(cw) == 1 and again.replayed and again.diff == first.diff
    assert first.affected == 1 and first.diff[0]["kind"] == "section"


def test_ac4_ac8_retry_same_command_id_one_parse_call(cw: CmdWorld) -> None:  # AC4, AC8
    parser, cid = Parser(exclude(cw.leaf1)), uuid.uuid4()
    for _ in range(2):
        cw.service.apply(cid, SESSION, CommandRequest("loại mục 1.1"), parse=parser)
    assert parser.calls == 1


def test_ac4_command_id_reused_different_payload_409(cw: CmdWorld) -> None:  # AC4
    cid = uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=cid, text="a")
    with pytest.raises(CommandIdReused):
        cw.run(exclude(cw.leaf1), command_id=cid, text="b")


def test_ac4_failing_op_rolls_back_whole_command(cw: CmdWorld) -> None:  # AC4
    ops = [
        *exclude(cw.leaf1),
        {
            "kind": "question_set_type",
            "question": str(cw.questions[0].id),
            "question_type": str(uuid.uuid4()),
        },
    ]
    with pytest.raises(CommandRejected):
        cw.run(ops)
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is False and rows(cw) == 0


def test_ac4_other_users_ids_rejected_no_leak(cw: CmdWorld, two_users: tuple[User, User]) -> None:
    bob = CmdWorld(cw.db, two_users[1])
    with pytest.raises(CommandRejected) as theirs:
        cw.run(exclude(bob.leaf1))
    with pytest.raises(CommandRejected) as nobody:
        cw.run([{"kind": "section_exclude", "sections": [str(uuid.uuid4())]}])
    assert theirs.value.code == nobody.value.code == "not_owned" and rows(cw) == 0
    cw.db.refresh(bob.leaf1)
    assert bob.leaf1.excluded is False


def test_ac4_command_id_collision_across_users(cw: CmdWorld, two_users: tuple[User, User]) -> None:
    bob = CmdWorld(cw.db, two_users[1])
    cid = uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=cid)
    mine = bob.run(exclude(bob.leaf2), command_id=cid)
    assert not mine.replayed and rows(cw) == 2
    assert CommandLogRepository(cw.db, two_users[1].id).by_command_id(cid) is not None


def test_ac4_large_command_runs_and_reports_count(cw: CmdWorld) -> None:  # AC4
    ops = [
        {"kind": "question_set_answer", "question": str(q.id), "text": "x"} for q in cw.questions
    ]
    out = cw.run(ops)
    assert out.affected == 3 and len(out.diff) == 3


@pytest.mark.parametrize("kind", ["section_set_pages", "question_relink", "card_delete", "unclear"])
def test_unregistered_op_422(cw: CmdWorld, kind: str) -> None:
    with pytest.raises(CommandRejected) as caught:
        cw.run([{"kind": kind, "section": str(cw.leaf1.id)}])
    assert caught.value.code == "unsupported" and rows(cw) == 0


def test_ac6_no_destructive_op_registered() -> None:  # AC6
    assert not {k for k in APPLICABLE_KINDS if "delete" in k or "reset" in k or "fsrs" in k}
    assert {"section_set_pages", "question_relink"}.isdisjoint(APPLICABLE_KINDS)


def test_ac9_command_log_has_ops_diff_inverse(cw: CmdWorld) -> None:  # AC9
    cid = uuid.uuid4()
    qid = str(cw.questions[0].id)
    cw.run([{"kind": "question_set_answer", "question": qid, "text": "đáp"}], command_id=cid)
    row = CommandLogRepository(cw.db, cw.user.id).by_command_id(cid)
    assert row and row.ops_json[0]["kind"] == "question_set_answer"
    entry = row.inverse_json[0]
    assert entry["after"]["answer"] == "đáp"
    assert entry["reverts"][0]["before"]["answer_text"] is None
    assert row.screen_session_id == SESSION and row.affected_count == 1


def test_inverse_expected_rev_matches_db_version(cw: CmdWorld) -> None:  # P1
    cid = uuid.uuid4()
    q = cw.questions[0]
    cw.run(
        [
            {"kind": "section_mark", "sections": [str(cw.parent.id)], "studied": True},
            {"kind": "question_set_answer", "question": str(q.id), "text": "t"},
        ],
        command_id=cid,
    )
    row = CommandLogRepository(cw.db, cw.user.id).by_command_id(cid)
    assert row and row.undo_revs_json is None  # the undo writes it, once
    cw.db.refresh(cw.leaf1)
    cw.db.refresh(q)
    revs = {r["id"]: r["expected_rev"] for e in row.inverse_json for r in e["reverts"]}
    assert revs[str(cw.leaf1.id)] == cw.leaf1.version
    assert cw.leaf1.studied_weight == cw.leaf1.weight


def test_section_exclude_goes_through_outline_rules(cw: CmdWorld) -> None:
    cw.run(exclude(cw.leaf2))
    cw.db.refresh(cw.leaf2)
    assert cw.leaf2.excluded and cw.leaf2.source == "user"


def test_study_filter_replaced_bumps_rev(cw: CmdWorld) -> None:
    sid = str(cw.subject.id)
    cw.run([{"kind": "suggest_only_subject", "subject": sid, "until": "2026-12-01"}])
    cw.run([{"kind": "suggest_defer_subject", "subject": sid, "until": "2026-12-01"}])
    state = StudyFilterRepository(cw.db, cw.user.id).state(cw.subject.id)
    assert state.mode == "defer" and state.rev == 2


def test_command_remove_and_button_write_same_log_row(cw: CmdWorld) -> None:  # F2
    q1, q2 = cw.questions[0], cw.questions[1]
    cid = uuid.uuid4()
    cw.run([{"kind": "question_remove_from_practice", "question": str(q1.id)}], command_id=cid)
    practice.remove(cw.db, cw.user.id, q2.id, datetime.now(UTC))
    logged = cw.db.scalars(select(PracticeRemovalLog).order_by(PracticeRemovalLog.id)).all()
    assert [(r.question_id, r.action) for r in logged] == [(q1.id, "removed"), (q2.id, "removed")]
    assert logged[0].command_id == cid and logged[1].command_id is None


def test_card_edit_merge_split_add_discard(cw: CmdWorld) -> None:
    c0, c1, c2 = (str(c.id) for c in cw.cards)
    cw.run([{"kind": "card_edit", "card": c0, "text": "mới"}])
    cw.db.refresh(cw.cards[0])
    assert cw.cards[0].summary == "mới" and cw.cards[0].version == 2
    out = cw.run([{"kind": "card_merge", "cards": [c1, c2]}])
    cw.db.refresh(cw.cards[1])
    cw.db.refresh(cw.cards[2])
    kept = min(cw.cards[1:], key=lambda u: (u.created_at, str(u.id)))
    assert "\n\n" in kept.summary and out.affected == 2
    assert {u.status for u in cw.cards[1:]} == {"draft", "merged"}
    split = cw.run([{"kind": "card_split", "card": str(kept.id), "parts": 2}])
    made = [d for d in split.diff if d["verb"] == "added"]
    assert len(made) == 1
    assert cw.db.get(KnowledgeUnit, uuid.UUID(made[0]["id"])).status == "draft"  # type: ignore[union-attr]
    text = "Thẻ do lệnh tạo\nchi tiết"
    add = cw.run([{"kind": "card_add", "text": text, "section": str(cw.leaf1.id)}])
    assert cw.db.get(KnowledgeUnit, uuid.UUID(add.diff[0]["id"])).title == "Thẻ do lệnh tạo"  # type: ignore[union-attr]
    cw.run([{"kind": "card_discard_draft", "card": c0}])
    cw.db.refresh(cw.cards[0])
    assert cw.cards[0].status == "retired"


def test_logs_and_errors_do_not_contain_raw_text(
    cw: CmdWorld, caplog: pytest.LogCaptureFixture
) -> None:  # P6
    caplog.set_level(logging.DEBUG)
    secret = "BIMAT-xyz"
    cw.service.apply(uuid.uuid4(), SESSION, CommandRequest(secret), parse=Parser(exclude(cw.leaf1)))
    bad = Parser([{"kind": f"x{secret}", "text": secret, secret: 1}])
    with pytest.raises(CommandRejected) as caught:
        cw.service.apply(uuid.uuid4(), SESSION, CommandRequest(secret), parse=bad)
    assert secret not in caplog.text
    assert secret not in str(caught.value) and secret not in caught.value.detail


def test_op_pair_that_cancels_keeps_its_reverts(cw: CmdWorld) -> None:  # review Y1
    cw.leaf1.studied_weight = 1.0
    cw.db.flush()
    cid = uuid.uuid4()
    pid = str(cw.leaf1.id)
    cw.run(
        [
            {"kind": "section_mark", "sections": [pid], "studied": True},
            {"kind": "section_mark", "sections": [pid], "studied": False},
        ],
        command_id=cid,
    )
    row = CommandLogRepository(cw.db, cw.user.id).by_command_id(cid)
    assert row
    reverts = [r for e in row.inverse_json for r in e["reverts"] if r["id"] == pid]
    assert reverts and reverts[0]["before"] == {"studied_weight": 1.0}


def test_study_filter_and_removal_log_isolated_two_users(
    cw: CmdWorld, two_users: tuple[User, User]
) -> None:
    bob = CmdWorld(cw.db, two_users[1])
    cw.run([{"kind": "suggest_only_subject", "subject": str(cw.subject.id), "until": "2026-12-01"}])
    cw.run([{"kind": "question_remove_from_practice", "question": str(cw.questions[0].id)}])
    assert StudyFilterRepository(cw.db, bob.user.id).state(cw.subject.id).rev == 0
    assert PracticeRemovalRepository(cw.db, bob.user.id).rev(cw.questions[0].id) == 0
    with pytest.raises(CommandRejected):
        bob.run([{"kind": "question_remove_from_practice", "question": str(cw.questions[0].id)}])


def test_ac4_removed_then_readded_question_survives_rebuild(cw: CmdWorld) -> None:  # review Y4
    from core_api.repositories.practice import PracticeStateRepository

    q = cw.questions[0]
    now = datetime.now(UTC)
    practice.remove(cw.db, cw.user.id, q.id, now)
    practice.readd(cw.db, cw.user.id, q.id, at=now)
    actions = [
        r.action for r in cw.db.scalars(select(PracticeRemovalLog).order_by(PracticeRemovalLog.id))
    ]
    assert actions == ["removed", "readded"]
    PracticeStateRepository(cw.db, cw.user.id).rebuild([q.id])
    assert PracticeRemovalRepository(cw.db, cw.user.id).in_practice(q.id)


def test_ac4_service_errors_become_codes_without_detail(cw: CmdWorld) -> None:
    # SectionNotFoundError / QuestionNotFoundError / NoChangeError / RangeError out of the
    # services the screens use are rejections with a code, not a 500 (final review Y1).
    from core_api.services.commands import CommandService

    service = cw.service
    ops = [{"kind": "section_exclude", "sections": [str(cw.leaf1.id)]}]
    from unittest.mock import patch

    from core_api.services.outline import NoChangeError, OutlineService, SectionNotFoundError

    for error, code in ((SectionNotFoundError, "not_owned"), (NoChangeError, "no_change")):
        with (
            patch.object(OutlineService, "edit_section", side_effect=error("BIMAT-xyz")),
            pytest.raises(CommandRejected) as caught,
        ):
            service.apply(uuid.uuid4(), SESSION, CommandRequest("x"), parse=Parser(ops))
        assert caught.value.code == code and "BIMAT" not in str(caught.value)
    assert rows(cw) == 0
    assert isinstance(service, CommandService)
