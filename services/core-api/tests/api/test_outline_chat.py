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
    res = chat(client, world, "bỏ mục 1.2")
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
    assert "hết lượt" in chat(client, world, "bỏ mục 1.2").json()["reply"]
    ai.failure = NotGraded("unavailable", "x")
    assert chat(client, world, "bỏ mục 1.2").json()["status"] == "failed"


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
