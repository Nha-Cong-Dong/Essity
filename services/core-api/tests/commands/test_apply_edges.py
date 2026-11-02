"""T9.2c edge cases from the tester (US-18 AC4, AC8; plan T9.2c 'Xong khi'): the request hash,
the validator's limits, a failure in the middle of the writes, the parser outside the transaction.
"""

import unicodedata
import uuid

import pytest
from sqlalchemy import func, select

from cmd_world import SESSION, CmdWorld, Parser
from core_api.db.models import CommandLog
from core_api.domain.commands.registry import CommandRejected
from core_api.services.command_codec import MAX_OPS, MAX_TEXT
from core_api.services.commands import CommandIdReused, CommandRequest
from v2_rows import make_unit


def rows(cw: CmdWorld) -> int:
    return cw.db.scalar(select(func.count()).select_from(CommandLog)) or 0


def exclude(*sections: object) -> list[dict[str, object]]:
    return [{"kind": "section_exclude", "sections": [str(s.id) for s in sections]}]  # type: ignore[attr-defined]


def answers(cw: CmdWorld, n: int, text: str = "x") -> list[dict[str, object]]:
    qs = cw.questions
    return [
        {"kind": "question_set_answer", "question": str(qs[i % len(qs)].id), "text": text}
        for i in range(n)
    ]


# --- AC4: the payload hash ------------------------------------------------------------------


def test_ac4_retry_in_nfd_is_the_same_command(cw: CmdWorld) -> None:
    # Red when: the hash skips NFC, so a retry typed in NFD is refused as command_id_reused.
    cid, text = uuid.uuid4(), "loại mục Đường cong"
    cw.run(exclude(cw.leaf1), command_id=cid, text=unicodedata.normalize("NFC", text))
    again = cw.run(exclude(cw.leaf1), command_id=cid, text=unicodedata.normalize("NFD", text))
    assert again.replayed and rows(cw) == 1


def test_ac4_trailing_space_is_another_payload(cw: CmdWorld) -> None:
    # Red when: the hash trims the text (plan: "NFC không trim").
    cid = uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=cid, text="a")
    with pytest.raises(CommandIdReused):
        cw.run(exclude(cw.leaf1), command_id=cid, text="a ")


def test_ac4_same_text_other_screen_session_is_reused(cw: CmdWorld) -> None:
    # Red when: the screen session is left out of the hash (the retry would be undone elsewhere).
    cid = uuid.uuid4()
    cw.run(exclude(cw.leaf1), command_id=cid, session_id=SESSION)
    with pytest.raises(CommandIdReused):
        cw.run(exclude(cw.leaf1), command_id=cid, session_id=uuid.UUID(int=2))


def test_ac4_client_ops_are_in_the_hash(cw: CmdWorld) -> None:
    # Red when: the client's ops are left out of the hash (other ops under one id replay).
    cid = uuid.uuid4()
    cw.service.apply(cid, SESSION, CommandRequest("", exclude(cw.leaf1)), parse=Parser())
    with pytest.raises(CommandIdReused):
        cw.service.apply(cid, SESSION, CommandRequest("", exclude(cw.leaf2)), parse=Parser())
    cw.db.refresh(cw.leaf2)
    assert cw.leaf2.excluded is False


def test_ac4_client_ops_key_order_does_not_matter(cw: CmdWorld) -> None:
    # Red when: the hash is not computed with sorted keys (a re-serialised retry gets 409).
    cid, sid = uuid.uuid4(), str(cw.leaf1.id)
    first = [{"kind": "section_exclude", "sections": [sid]}]
    second = [{"sections": [sid], "kind": "section_exclude"}]
    cw.service.apply(cid, SESSION, CommandRequest("", first), parse=Parser())
    again = cw.service.apply(cid, SESSION, CommandRequest("", second), parse=Parser())
    assert again.replayed


def test_ac4_client_ops_never_call_the_parser(cw: CmdWorld) -> None:
    # Red when: ops sent by the client still go through the LLM parser.
    parser = Parser(exclude(cw.leaf2))
    cw.service.apply(uuid.uuid4(), SESSION, CommandRequest("x", exclude(cw.leaf1)), parse=parser)
    cw.db.refresh(cw.leaf1)
    assert parser.calls == 0 and cw.leaf1.excluded


def test_ac4_replay_reports_the_stored_affected_count(cw: CmdWorld) -> None:
    # Red when: the log stores the number of ops instead of the number of changed objects.
    cid = uuid.uuid4()
    first = cw.run(exclude(cw.leaf1, cw.leaf2), command_id=cid)
    again = cw.run(exclude(cw.leaf1, cw.leaf2), command_id=cid)
    assert first.affected == 2 and again.affected == 2 and again.diff == first.diff


# --- AC8: the parser runs outside the transaction --------------------------------------------


def test_ac8_parser_runs_with_no_transaction_open(cw: CmdWorld) -> None:
    # Red when: the read of the replay check stays open (locks/snapshot) across the LLM call.
    seen: list[bool] = []

    def parse(raw_text: str) -> list[dict[str, object]]:
        seen.append(cw.db.in_transaction())
        return exclude(cw.leaf1)

    cw.service.apply(uuid.uuid4(), SESSION, CommandRequest("loại 1.1"), parse=parse)
    assert seen == [False]


# --- AC4: one validator, its limits -----------------------------------------------------------


def test_ac4_empty_parse_is_rejected(cw: CmdWorld) -> None:
    # Red when: a parse with no op writes a log row (an empty command looks applied).
    with pytest.raises(CommandRejected) as caught:
        cw.run([])
    assert caught.value.code == "empty_command" and rows(cw) == 0


def test_ac4_max_ops_boundary(cw: CmdWorld) -> None:
    # Red when: MAX_OPS ops are refused, or MAX_OPS + 1 ops run.
    assert cw.run(answers(cw, MAX_OPS)).affected == len(cw.questions)
    with pytest.raises(CommandRejected) as caught:
        cw.run(answers(cw, MAX_OPS + 1))
    assert caught.value.code == "too_many_ops" and rows(cw) == 1


def test_ac4_max_text_boundary(cw: CmdWorld) -> None:
    # Red when: a text of MAX_TEXT chars is refused, or one of MAX_TEXT + 1 is stored.
    cw.run(answers(cw, 1, "a" * MAX_TEXT))
    with pytest.raises(CommandRejected) as caught:
        cw.run(answers(cw, 1, "b" * (MAX_TEXT + 1)))
    assert caught.value.code == "text_too_long" and rows(cw) == 1


def test_ac4_non_dict_op_is_rejected(cw: CmdWorld) -> None:
    # Red when: a malformed op (not an object) from the LLM crashes instead of a 422.
    with pytest.raises(CommandRejected):
        cw.run(["section_exclude"])  # type: ignore[list-item]


# --- AC4: a failure in the middle of the writes ---------------------------------------------


def test_ac4_failure_after_a_write_rolls_back_the_written_op(cw: CmdWorld) -> None:
    # Red when: the command has no savepoint: the section written by op 1 stays excluded after
    # op 2 fails in its write (a caller that catches CommandRejected would commit half a command).
    canonical = make_unit(cw.db, cw.user, cw.subject, status="canonical")
    ops = [*exclude(cw.leaf1), {"kind": "card_edit", "card": str(canonical.id), "text": "y"}]
    with pytest.raises(CommandRejected) as caught:
        cw.run(ops)
    assert caught.value.code == "canonical_card"
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.excluded is False and rows(cw) == 0


def test_merge_diff_names_the_card_the_database_kept(cw: CmdWorld) -> None:
    # Red when: the domain runs the merge in the op's order while the review service keeps the
    # oldest card: the diff (and the inverse built from it) says the other card survived.
    c1, c2 = cw.cards[1], cw.cards[2]
    kept, other = sorted([c1, c2], key=lambda u: (u.created_at, str(u.id)))
    out = cw.run([{"kind": "card_merge", "cards": [str(other.id), str(kept.id)]}])
    status = {d["id"]: d["after"]["status"] for d in out.diff}
    assert status == {str(kept.id): "draft", str(other.id): "discarded"}


def test_p6_unknown_field_name_not_in_error(cw: CmdWorld) -> None:
    # Red when: the validator hands back op_from_json's detail (the unknown field names, which
    # come from the LLM and may echo the learner's text).
    secret = "BIMAT-xyz"
    op = {"kind": "section_exclude", "sections": [str(cw.leaf1.id)], secret: 1}
    with pytest.raises(CommandRejected) as caught:
        cw.run([op])
    assert caught.value.code == "unknown_fields" and secret not in caught.value.detail


def test_remove_from_practice_inverse_holds_in_practice_and_log_rev(cw: CmdWorld) -> None:
    # Red when: the revert of a removal does not say the question was in practice, or its
    # expected_rev is not the id of the log row just written (T9.2d's undo checks it).
    from core_api.repositories.command_log import CommandLogRepository
    from core_api.repositories.practice_removal import PracticeRemovalRepository

    q, cid = cw.questions[0], uuid.uuid4()
    cw.run([{"kind": "question_remove_from_practice", "question": str(q.id)}], command_id=cid)
    row = CommandLogRepository(cw.db, cw.user.id).by_command_id(cid)
    assert row
    (revert,) = [r for e in row.inverse_json for r in e["reverts"]]
    rev = PracticeRemovalRepository(cw.db, cw.user.id).rev(q.id)
    assert revert["table"] == "practice_removal" and revert["before"] == {"in_practice": True}
    assert rev > 0 and revert["expected_rev"] == rev
