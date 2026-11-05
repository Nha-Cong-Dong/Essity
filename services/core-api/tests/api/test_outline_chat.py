# ruff: noqa: F811, F401
"""E3: `POST /v1/subjects/{id}/outline/chat`: plain Vietnamese in, a short Vietnamese reply out.
The parser is a double; only outline operations may run, everything else is a friendly hint."""

from typing import Any

from fastapi.testclient import TestClient
from test_commands_api import FakeAi, World, ai, world  # pyright: ignore[reportUnusedImport]  (fixtures)

from core_api.clients.ai_client import NotGraded


def chat(client: TestClient, w: World, text: str) -> Any:
    cw, h = w
    return client.post(f"/v1/subjects/{cw.subject.id}/outline/chat", json={"text": text}, headers=h)


def test_leave_out_by_sentence_replies_in_vietnamese(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, _ = world
    ai.result = {"kind": "section_exclude", "sections": [str(cw.leaf2.id)]}
    res = chat(client, world, "bỏ cái gì đó không rõ")
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["status"] == "applied" and out["affected"] == 1 and out["command_id"]
    assert "Đã bỏ 1 mục" in out["reply"]
    cw.db.refresh(cw.leaf2)
    assert cw.leaf2.excluded is True


def test_unclear_sentence_gets_examples(client: TestClient, ai: FakeAi, world: World) -> None:
    out = chat(client, world, "làm cho đẹp hơn").json()
    assert out["status"] == "unclear" and "bỏ phần phụ lục" in out["reply"]


def test_card_operation_is_not_an_outline_operation(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, _ = world
    ai.result = {"kind": "card_merge", "cards": [str(cw.cards[0].id), str(cw.cards[1].id)]}
    out = chat(client, world, "gộp thẻ 1 và 2").json()
    assert out["status"] == "unclear" and out["command_id"] is None


def test_quota_and_outage_are_friendly(client: TestClient, ai: FakeAi, world: World) -> None:
    ai.failure = NotGraded("quota", "x")
    assert "hết lượt" in chat(client, world, "bỏ cái gì đó không rõ").json()["reply"]
    ai.failure = NotGraded("unavailable", "x")
    assert chat(client, world, "bỏ cái gì đó không rõ").json()["status"] == "failed"


def test_other_users_subject_is_404(client: TestClient, ai: FakeAi, world: World) -> None:
    import uuid

    _, h = world
    res = client.post(f"/v1/subjects/{uuid.uuid4()}/outline/chat", json={"text": "bỏ"}, headers=h)
    assert res.status_code == 404


def test_merge_siblings_by_sentence(client: TestClient, ai: FakeAi, world: World) -> None:
    cw, _ = world
    out = chat(client, world, "Gộp mục 1.1 với 1.2").json()
    assert out["status"] == "applied" and "Đã gộp 2 mục" in out["reply"], out
    assert ai.payloads == []  # read by pattern, no model call
    from sqlalchemy import select

    from core_api.db.models import DocSection

    titles = set(
        cw.db.scalars(select(DocSection.title).where(DocSection.subject_id == cw.subject.id))
    )
    assert "1.1" in titles and "1.2" not in titles


def test_merge_unknown_section_is_a_friendly_failure(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    out = chat(client, world, "gộp mục 1.1 với 9.9").json()
    assert out["status"] == "failed" and "9.9" in out["reply"]


def test_split_leaf_into_parts_by_pages(client: TestClient, ai: FakeAi, world: World) -> None:
    cw, _ = world
    cw.leaf2.first_page, cw.leaf2.last_page = 10, 19
    cw.db.flush()
    out = chat(client, world, "tách mục 1.2 thành 2 phần").json()
    assert out["status"] == "applied", out
    from sqlalchemy import select

    from core_api.db.models import DocSection

    rows = cw.db.execute(
        select(DocSection.title, DocSection.first_page, DocSection.last_page)
        .where(DocSection.title.like("1.2 (phần%"))
        .order_by(DocSection.title)
    ).all()
    assert [(r[1], r[2]) for r in rows] == [(10, 14), (15, 19)]


def test_split_chapter_promotes_its_children(client: TestClient, ai: FakeAi, world: World) -> None:
    cw, _ = world
    cw.parent.title = "Chương 1"
    cw.db.flush()
    out = chat(client, world, "tách chương 1").json()
    assert out["status"] == "applied" and "2 mục" in out["reply"], out
    cw.db.refresh(cw.leaf1)
    assert cw.leaf1.parent_id is None


def _titles(cw: Any) -> dict[str, Any]:
    from sqlalchemy import select

    from core_api.db.models import DocSection

    return {
        r.title: r
        for r in cw.db.scalars(select(DocSection).where(DocSection.subject_id == cw.subject.id))
    }


def _retitle(cw: Any) -> None:
    cw.parent.title = "Phần 1"
    cw.leaf1.title = "Bài tập chương 3"
    cw.leaf2.title = "Bài tập chương 4"
    cw.db.flush()


def test_q25_leave_out_by_title_needs_no_model(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, _ = world
    _retitle(cw)
    for text, target in [
        ("bỏ Bài tập chương 3 khỏi đề cương", cw.leaf1),
        ("Loại bỏ bài tập chương 4.", cw.leaf2),
    ]:
        out = chat(client, world, text).json()
        assert out["status"] == "applied" and out["command_id"], (text, out)
        cw.db.refresh(target)
        assert target.excluded is True
    assert ai.payloads == []  # never reached the model


def test_q25_leave_out_variants_and_fallback(client: TestClient, ai: FakeAi, world: World) -> None:
    cw, _ = world
    _retitle(cw)
    cw.db.flush()
    out = chat(client, world, "bỏ chương 3 và chương 4").json()  # two targets, one command
    assert out["status"] == "applied" and out["affected"] == 2, out
    out = chat(client, world, "bỏ bai tap chuong 3").json()  # no accents: already out
    assert out["status"] == "applied" and "đã đúng" in out["reply"], out
    assert ai.payloads == []
    chat(client, world, "bỏ cái không có trong đề cương")  # names nothing: the model decides
    assert len(ai.payloads) == 1


def test_q25_ambiguous_title_goes_to_the_model(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, _ = world
    cw.leaf1.title, cw.leaf2.title = "Bài tập A", "Bài tập B"
    cw.db.flush()
    chat(client, world, "bỏ bài tập")
    assert len(ai.payloads) == 1 and cw.leaf1.excluded is False


def test_q25_mark_studied_by_title(client: TestClient, ai: FakeAi, world: World) -> None:
    cw, _ = world
    _retitle(cw)
    out = chat(client, world, "đánh dấu bài tập chương 3 là đã học").json()
    assert out["status"] == "applied" and out["command_id"], out
    assert ai.payloads == []


def test_q25_merge_is_a_command_and_undo_restores(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    import uuid

    from core_api.db.models import DocSection

    cw, h = world
    cw.leaf1.first_page, cw.leaf1.last_page = 1, 5
    cw.leaf2.first_page, cw.leaf2.last_page = 6, 9
    child = DocSection(
        subject_id=cw.subject.id, document_id=cw.document.id, parent_id=cw.leaf2.id, ord=0,
        title="1.2.1", weight=1, studied_weight=0, unit="page", source="user",
    )  # fmt: skip
    child.id, child.user_id = uuid.uuid4(), cw.leaf2.user_id
    cw.db.add(child)
    cw.db.flush()
    leaf1_id, leaf2_id, child_id = cw.leaf1.id, cw.leaf2.id, child.id
    out = chat(client, world, "gộp 1.1 với 1.2").json()
    assert out["status"] == "applied" and out["command_id"], out
    assert "Đã gộp 2 mục" in out["reply"] and ai.payloads == []
    cw.db.expire_all()
    rows = _titles(cw)
    assert "1.2" not in rows and rows["1.1"].last_page == 9
    assert rows["1.2.1"].parent_id == leaf1_id
    res = client.post(f"/v1/commands/{out['command_id']}/undo", headers=h)
    assert res.status_code == 200, res.text
    cw.db.expire_all()
    rows = _titles(cw)
    assert rows["1.2"].id == leaf2_id and rows["1.2"].parent_id == cw.parent.id
    assert (rows["1.2"].first_page, rows["1.2"].last_page) == (6, 9)
    assert (rows["1.1"].first_page, rows["1.1"].last_page) == (1, 5)
    assert rows["1.1"].weight == 2 and rows["1.2"].weight == 2
    assert rows["1.2.1"].id == child_id and rows["1.2.1"].parent_id == leaf2_id


def test_q25_merge_undo_refused_after_later_edit(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, h = world
    out = chat(client, world, "gộp 1.1 với 1.2").json()
    first = _titles(cw)["1.1"]
    first.weight += 1  # something moved the merged section on
    cw.db.flush()
    res = client.post(f"/v1/commands/{out['command_id']}/undo", headers=h)
    assert res.status_code == 409, res.text


def test_q25_chapter_number_does_not_pick_a_title_that_ends_with_it(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, _ = world
    cw.leaf1.title, cw.leaf2.title = "3. Xác suất", "Bài tập chương 3"
    cw.db.flush()
    chat(client, world, "bỏ chương 3")  # fits both: the model decides, nothing is left out
    assert len(ai.payloads) == 1
    cw.db.refresh(cw.leaf1)
    cw.db.refresh(cw.leaf2)
    assert cw.leaf1.excluded is False and cw.leaf2.excluded is False


def test_q25_merge_undo_by_another_user_is_404(
    client: TestClient, ai: FakeAi, db_session: Any, two_users: Any
) -> None:
    from test_commands_api import CmdWorld, headers_of

    alice, bob = two_users
    a = CmdWorld(db_session, alice)
    out = chat(client, (a, headers_of(db_session, alice)), "gộp 1.1 với 1.2").json()
    assert out["status"] == "applied", out
    res = client.post(f"/v1/commands/{out['command_id']}/undo", headers=headers_of(db_session, bob))
    assert res.status_code == 404 and res.json() == {"detail": "not_owned"}
    db_session.expire_all()
    assert "1.2" not in _titles(a)  # still merged


def test_q25_merge_of_a_section_with_cards_is_refused(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    from core_api.db.models import UnitSection

    cw, _ = world
    unit = cw.cards[0]
    cw.db.add(
        UnitSection(
            user_id=cw.user.id, subject_id=cw.subject.id, unit_id=unit.id, section_id=cw.leaf2.id
        )
    )
    cw.db.flush()
    out = chat(client, world, "gộp 1.1 với 1.2").json()
    assert out["status"] == "failed" and "gắn thẻ" in out["reply"], out


def test_q25_merge_of_a_section_with_cards_is_refused_on_the_command_route(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    from test_commands_api import post

    from core_api.db.models import UnitSection

    cw, h = world
    cw.db.add(
        UnitSection(
            user_id=cw.user.id,
            subject_id=cw.subject.id,
            unit_id=cw.cards[0].id,
            section_id=cw.leaf2.id,
        )
    )
    cw.db.flush()
    ops = [{"kind": "section_merge", "sections": [str(cw.leaf1.id), str(cw.leaf2.id)]}]
    res = post(client, h, {"ops": ops})
    assert res.status_code == 422, res.text
    cw.db.expire_all()
    assert "1.2" in _titles(cw)


def test_q25_merge_retry_with_same_command_id_answers_from_the_log(
    client: TestClient, ai: FakeAi, world: World
) -> None:
    cw, h = world
    cid = str(__import__("uuid").uuid4())
    url = f"/v1/subjects/{cw.subject.id}/outline/chat"
    body = {"text": "gộp 1.1 với 1.2", "command_id": cid}
    first = client.post(url, json=body, headers=h).json()
    again = client.post(url, json=body, headers=h).json()
    assert first["status"] == "applied" and again["status"] == "applied", again
    assert again["command_id"] == cid and "Đã gộp 2 mục" in again["reply"]
