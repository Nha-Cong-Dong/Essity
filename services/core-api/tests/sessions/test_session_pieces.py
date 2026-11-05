# ruff: noqa: F811
# pyright: reportUnusedImport=false
"""F2/F3: a study session in pieces. Each piece is kept at once; completing hands them in as one
submission."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_submissions import World, enabled, world  # noqa: F401  (fixtures)

from core_api.db.models import SessionPiece, Submission, User

pytestmark = pytest.mark.usefixtures("fake_storage", "enabled")


def piece(client: TestClient, world: World, **body: object):  # noqa: ANN201
    return client.post(
        f"/v1/study-sessions/{world.draft.id}/pieces", json=body, headers=world.headers
    )


def test_pieces_are_kept_and_listed_in_order(client: TestClient, world: World) -> None:
    assert piece(client, world, text="Mảnh một").status_code == 201
    assert piece(client, world, text="Mảnh hai", files=[world.pdf()]).status_code == 201
    listed = client.get(f"/v1/study-sessions/{world.draft.id}/pieces", headers=world.headers)
    body = listed.json()
    assert [p["text"] for p in body["pieces"]] == ["Mảnh một", "Mảnh hai"]
    assert [p["file_count"] for p in body["pieces"]] == [0, 1]
    assert body["submitted"] is False


def test_empty_piece_refused(client: TestClient, world: World) -> None:
    assert piece(client, world, text="  ").status_code == 422


def test_complete_makes_one_submission_from_all_pieces(client: TestClient, world: World) -> None:
    piece(client, world, text="Mảnh một")
    piece(client, world, text="Mảnh hai")
    done = client.post(f"/v1/study-sessions/{world.draft.id}/complete", headers=world.headers)
    assert done.status_code == 201, done.text
    assert done.json()["status"] == "queued"
    assert world.db.scalar(select(func.count()).select_from(Submission)) == 1
    assert world.db.scalar(select(func.count()).select_from(SessionPiece)) == 2
    again = piece(client, world, text="Muộn")
    assert again.status_code == 409
    listed = client.get(f"/v1/study-sessions/{world.draft.id}/pieces", headers=world.headers)
    assert listed.json()["submitted"] is True


def test_complete_without_pieces_refused(client: TestClient, world: World) -> None:
    done = client.post(f"/v1/study-sessions/{world.draft.id}/complete", headers=world.headers)
    assert done.status_code == 422


def test_complete_marks_the_given_section_studied(client: TestClient, world: World) -> None:
    from core_api.db.models import DocSection  # noqa: PLC0415

    piece(client, world, text="Mảnh một")
    done = client.post(
        f"/v1/study-sessions/{world.draft.id}/complete",
        json={"section_id": str(world.chapter.id)},
        headers=world.headers,
    )
    assert done.status_code == 201, done.text
    world.db.expire_all()
    row = world.db.scalars(select(DocSection).where(DocSection.id == world.chapter.id)).one()
    assert row.weight > 0
    assert row.studied_weight >= row.weight


def test_a_piece_can_be_dropped_before_the_session_is_handed_in(
    client: TestClient, world: World
) -> None:
    # Red when: a piece that cannot be completed (a bad @) leaves the session stuck for good.
    first = piece(client, world, text="Mảnh một").json()
    piece(client, world, text="Mảnh hai")
    url = f"/v1/study-sessions/{world.draft.id}/pieces/{first['id']}"
    assert client.delete(url, headers=world.headers).status_code == 204
    listed = client.get(f"/v1/study-sessions/{world.draft.id}/pieces", headers=world.headers)
    assert [p["text"] for p in listed.json()["pieces"]] == ["Mảnh hai"]
    assert client.delete(url, headers=world.headers).status_code == 404


def test_a_piece_cannot_be_dropped_once_handed_in_or_by_a_stranger(
    client: TestClient, world: World
) -> None:
    from accounts import signed_in  # noqa: PLC0415

    made = piece(client, world, text="Mảnh một").json()
    url = f"/v1/study-sessions/{world.draft.id}/pieces/{made['id']}"
    stranger = signed_in(world.db)[1]
    assert client.delete(url, headers=stranger).status_code == 404
    client.post(f"/v1/study-sessions/{world.draft.id}/complete", headers=world.headers)
    assert client.delete(url, headers=world.headers).status_code == 409
    assert world.db.scalar(select(func.count()).select_from(SessionPiece)) == 1


def test_dropping_a_piece_refuses_an_unverified_user(
    client: TestClient, db_session: Session, unverified_user: User
) -> None:
    # Red when: the route drops VerifiedUser and lets an unverified account change a session.
    from datetime import UTC, datetime  # noqa: PLC0415
    from uuid import uuid4  # noqa: PLC0415

    from core_api.repositories.auth_session import AuthSessionRepository  # noqa: PLC0415

    token, _ = AuthSessionRepository(db_session).create(unverified_user.id, datetime.now(UTC))
    response = client.delete(
        f"/v1/study-sessions/{uuid4()}/pieces/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_complete_hands_in_only_the_pieces_left_after_a_drop(
    client: TestClient, world: World
) -> None:
    # Red when: complete reads pieces without the session lock a drop takes, so a piece dropped at
    # the same moment can still be handed in (here: the order drop, complete, then drop again).
    keep = piece(client, world, text="Giữ lại").json()
    gone = piece(client, world, text="Bỏ đi").json()
    base = f"/v1/study-sessions/{world.draft.id}/pieces"
    assert client.delete(f"{base}/{gone['id']}", headers=world.headers).status_code == 204
    done = client.post(f"/v1/study-sessions/{world.draft.id}/complete", headers=world.headers)
    assert done.status_code == 201, done.text
    # the lock is the same row lock `drop_piece` takes: it is free again after the commit
    assert client.delete(f"{base}/{keep['id']}", headers=world.headers).status_code == 409
    assert world.db.scalar(select(func.count()).select_from(SessionPiece)) == 1
