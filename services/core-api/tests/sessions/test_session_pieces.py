# ruff: noqa: F811
# pyright: reportUnusedImport=false
"""F2/F3: a study session in pieces. Each piece is kept at once; completing hands them in as one
submission."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_submissions import World, enabled, world  # noqa: F401  (fixtures)

from core_api.db.models import SessionPiece, Submission

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
