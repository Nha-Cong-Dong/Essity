"""T9.2e tester: edge cases of the command routes not covered by test_commands.py (US-18 AC3, AC4,
AC6, AC7; ADR-0030): the parser's answer is untrusted (another user's id, an op outside the list,
an unknown reason), what the parser is told (only this user's rows, titles cut and cleaned, lists
cut at the parser's limits) and the suggestion filter of one user never reaching another."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_commands import (
    FakeAi,
    World,
    exclude,
    log_count,
    post,
    shown,
    three_subjects,
    undo,
)
from test_suggestions import TODAY, headers_of

from clock import FROZEN_NOW
from cmd_world import CmdWorld
from core_api.api.commands import MAX_CLIENT_OPS, refusal
from core_api.api.ping import get_ai_client
from core_api.db.models import UnitSection, User
from core_api.domain.commands.registry import CommandRejected
from core_api.main import app
from core_api.services import command_context
from core_api.services.command_context import (
    MAX_DOCUMENTS,
    MAX_ITEMS,
    MAX_TITLE,
    MAX_TOTAL,
    _fit,  # pyright: ignore[reportPrivateUsage]
    _title,  # pyright: ignore[reportPrivateUsage]
)
from core_api.services.suggestions import learning_today
from v2_rows import make_document, make_section


@pytest.fixture
def ai() -> Iterator[FakeAi]:
    fake = FakeAi()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


@pytest.fixture
def world(db_session: Session, two_users: tuple[User, User]) -> World:
    return CmdWorld(db_session, two_users[0]), headers_of(db_session, two_users[0])


def test_ac4_parser_naming_another_users_section_is_404_and_writes_nothing(
    client: TestClient, ai: FakeAi, db_session: Session, two_users: tuple[User, User]
) -> None:  # AC4 isolation, ADR-0014 (the model's answer is data, not a permission)
    # Red when: an op the parser returns skips the per-user id check that client ops get.
    alice, bob = two_users
    a, b = CmdWorld(db_session, alice), CmdWorld(db_session, bob)
    ha = headers_of(db_session, alice)
    ai.result = {"kind": "section_exclude", "sections": [str(b.leaf1.id)]}
    r = post(client, ha, {"text": "bỏ mục 1.1", "subject_id": str(a.subject.id)})
    assert r.status_code == 404 and r.json() == {"detail": "not_owned"}
    db_session.refresh(b.leaf1)
    assert b.leaf1.excluded is False and log_count(db_session) == 0


def test_ac6_parser_answer_outside_the_fixed_list_is_422(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # AC6
    # Red when: an op the parser invents (or one not registered) runs, or is logged.
    cw, h = world
    ai.result = {"kind": "section_set_pages", "section": str(cw.leaf1.id), "from_page": 1}
    r = post(client, h, {"text": "đặt trang", "subject_id": str(cw.subject.id)})
    assert r.status_code == 422 and r.json() == {"detail": "unsupported"}
    assert log_count(cw.db) == 0


def test_ac3_an_unknown_unclear_reason_reads_as_ambiguous(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # AC3
    # Red when: a reason outside the four is echoed back (it would break the response schema),
    # or mapped to another known reason.
    cw, h = world
    ai.result = {"kind": "unclear", "reason": "<b>xin chào</b>"}
    r = post(client, h, {"text": "??", "subject_id": str(cw.subject.id)})
    assert r.status_code == 200 and r.json() == {"status": "unclear", "reason": "ambiguous"}
    assert log_count(cw.db) == 0


def test_ac7_parser_context_holds_only_this_users_ids_and_no_card_text(
    client: TestClient, ai: FakeAi, db_session: Session, two_users: tuple[User, User]
) -> None:  # AC7, isolation
    # Red when: a repository in build_parse_payload reads without user_id, or a card's summary
    # (its text) is sent to the parser.
    alice, bob = two_users
    a, b = CmdWorld(db_session, alice), CmdWorld(db_session, bob)
    post(client, headers_of(db_session, alice), {"text": "x", "subject_id": str(a.subject.id)})
    payload = str(ai.payloads[0])
    theirs = [b.subject, b.document, b.parent, b.leaf1, b.leaf2, b.qtype, *b.cards, *b.questions]
    assert not [row.id for row in theirs if str(row.id) in payload]
    assert "Nội dung" not in payload and "dòng hai" not in payload


def test_ac7_titles_are_cut_cleaned_and_never_empty() -> None:
    # Red when: a title goes over the parser's 120 characters, keeps a NUL or a line break, or a
    # blank title is sent empty (the parser rejects the whole request).
    long = "a\x00b\n" + "x" * 500
    cut = _title(long, "Thẻ")
    assert len(cut) == MAX_TITLE == 120 and "\x00" not in cut and "\n" not in cut
    assert cut.startswith("a b x")
    assert _title(" \x00\n\t ", "Thẻ") == "Thẻ"


def test_ac7_fit_trims_the_longest_list_under_the_total() -> None:
    # Red when: the lists stay over the parser's 60 000 characters (it would answer 422 and the
    # command bar would fail), or a short list loses rows before the longest one.
    item = {"id": "i", "title": "t" * 120}
    lists: dict[str, list[dict[str, Any]]] = {
        "cards": [dict(item) for _ in range(200)],
        "sections": [dict(item) for _ in range(200)],
        "questions": [dict(item) for _ in range(150)],
        "subjects": [dict(item)],
    }
    _fit(lists)
    total = sum(len(i["title"]) for items in lists.values() for i in items)
    assert 60_000 - 120 < total <= 60_000 == MAX_TOTAL
    assert len(lists["subjects"]) == 1 and len(lists["questions"]) == 150


def test_ac7_sections_are_cut_at_the_parsers_list_limit(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # AC7
    # Red when: more than 200 sections reach the parser (ai-service answers 422 for the whole
    # command), or the cut drops the first ones instead of the tail.
    cw, h = world
    extra = [
        make_section(cw.db, cw.user, cw.document, ord=10 + i, title=f"Mục {i}") for i in range(200)
    ]
    post(client, h, {"text": "x", "subject_id": str(cw.subject.id)})
    sections = ai.payloads[0]["sections"]
    assert len(sections) == 200 == MAX_ITEMS
    assert sections[0]["id"] == str(cw.parent.id)
    assert str(extra[-1].id) not in {s["id"] for s in sections}


def test_us15_ac9_one_users_filter_never_changes_anothers_suggestions(
    client: TestClient, ai: FakeAi, db_session: Session, two_users: tuple[User, User]
) -> None:  # US-15 AC9, isolation
    # Red when: command_filters reads study_filter rows of every user (B's A would be hidden).
    alice, bob = two_users
    ha, hb = headers_of(db_session, alice), headers_of(db_session, bob)
    a, _, _ = three_subjects(db_session, alice)
    three_subjects(db_session, bob)
    until = (TODAY + timedelta(days=4)).isoformat()
    ops = [{"kind": "suggest_defer_subject", "subject": str(a.id), "until": until}]
    cid = uuid.uuid4()
    assert post(client, ha, {"ops": ops}, cid).status_code == 200
    assert shown(client, ha) == ["B", "C"]
    assert shown(client, hb) == ["A", "B"]
    assert undo(client, ha, cid).status_code == 200


def test_ac5_undo_route_unknown_and_malformed_ids(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # AC5
    # Red when: undo of a malformed id is a 500, or of an unknown id is anything but 404.
    cw, h = world
    post(client, h, {"ops": exclude(cw.leaf1)})
    assert client.post("/v1/commands/not-a-uuid/undo", headers=h).status_code == 422
    assert undo(client, h, uuid.uuid4()).json() == {"detail": "not_owned"}


@pytest.mark.parametrize(
    "code", ["not_latest", "other_session", "conflict", "nothing_to_undo", "id_collision"]
)
def test_every_refusal_the_client_may_retry_is_409(code: str) -> None:
    # Red when: a conflict code of undo/apply falls back to 422 (the web would say "the command
    # cannot run" instead of "something changed, try again").
    error = refusal(CommandRejected(code, "an id"))
    assert (error.status_code, error.detail) == (409, code)


def test_more_ops_than_the_cap_are_422(client: TestClient, ai: FakeAi, world: World) -> None:
    # Red when: a client can send more than MAX_CLIENT_OPS ops in one command (locks held for an
    # unbounded list, ADR-0014 "at most N ops").
    cw, h = world
    one = exclude(cw.leaf1)[0]
    assert post(client, h, {"ops": [one] * (MAX_CLIENT_OPS + 1)}).status_code == 422
    assert log_count(cw.db) == 0


def test_parser_today_is_the_users_learning_day(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # US-15 AC10 (the day of "until Friday")
    # Red when: the parser is told the UTC date instead of the user's learning day.
    cw, h = world
    cw.user.timezone = "Pacific/Kiritimati"  # UTC+14: FROZEN_NOW is already the next day there
    cw.user.day_start_hour = 0
    cw.db.flush()
    post(client, h, {"text": "x", "subject_id": str(cw.subject.id)})
    expected = learning_today(cw.user, FROZEN_NOW)
    assert expected != FROZEN_NOW.date()
    assert ai.payloads[0]["today"] == expected.isoformat()


def test_y1_a_card_in_two_sections_sits_at_the_first_one(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # T9.1 Y1
    # Red when: a card linked to two sections is placed by the later one.
    cw, h = world
    first, second, third = cw.cards
    for i, card in enumerate(cw.cards):
        card.created_at = FROZEN_NOW - timedelta(hours=3 - i)
    links = ((first, cw.leaf2), (second, cw.leaf2), (third, cw.leaf2), (third, cw.leaf1))
    for card, section in links:
        cw.db.add(
            UnitSection(
                user_id=cw.user.id, subject_id=cw.subject.id, unit_id=card.id, section_id=section.id
            )
        )
    cw.db.flush()
    post(client, h, {"text": "x", "subject_id": str(cw.subject.id)})
    assert [c["id"] for c in ai.payloads[0]["cards"]] == [str(c.id) for c in (third, first, second)]


def test_ac7_the_route_keeps_the_parser_request_under_its_total(
    client: TestClient, ai: FakeAi, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:  # AC7
    # Red when: build_parse_payload does not trim to the total (ai-service would 422 the command).
    cw, h = world
    monkeypatch.setattr(command_context, "MAX_TOTAL", 30)
    post(client, h, {"text": "x", "subject_id": str(cw.subject.id)})
    lists = ("cards", "sections", "subjects", "question_types", "questions", "documents")
    total = sum(len(i["title"]) for k in lists for i in ai.payloads[0][k])
    assert 0 < total <= 30


def test_ac7_documents_are_cut_at_the_parsers_limit(
    client: TestClient, ai: FakeAi, world: World
) -> None:  # AC7
    # Red when: more than 50 documents reach the parser (it answers 422 for the whole command).
    cw, h = world
    for i in range(MAX_DOCUMENTS):
        make_document(cw.db, cw.user, cw.subject, sha=f"{i + 1:064x}", short_name=f"Tài liệu {i}")
    post(client, h, {"text": "x", "subject_id": str(cw.subject.id)})
    documents = ai.payloads[0]["documents"]
    assert len(documents) == MAX_DOCUMENTS
