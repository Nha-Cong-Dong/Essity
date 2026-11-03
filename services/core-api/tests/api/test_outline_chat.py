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
