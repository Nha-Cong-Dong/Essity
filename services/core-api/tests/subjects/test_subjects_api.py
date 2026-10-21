"""T1.19: `/v1/subjects` (US-01 AC1, AC2; ADR-0001, ADR-0014; plan B11–B13, B16, B17).

Dates are relative to the user's learning day now, so the tests hold whatever day they run.
"""

import unicodedata
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import User
from core_api.domain.learning_day import learning_day
from core_api.main import app


def today(user: User) -> date:
    return learning_day(datetime.now(UTC), ZoneInfo(user.timezone), user.day_start_hour)


def in_days(user: User, days: int) -> str:
    return (today(user) + timedelta(days=days)).isoformat()


def create(client: TestClient, headers: dict[str, str], name: str, exam_date: str) -> Any:
    return client.post("/v1/subjects", json={"name": name, "exam_date": exam_date}, headers=headers)


def error_field(response: Any) -> str:
    assert response.status_code == 422
    detail = response.json()["detail"]
    return detail if isinstance(detail, str) else detail[0]["loc"][-1]


# --- POST (AC1, AC2) --------------------------------------------------------------------------


def test_ac1_create_returns_the_subject(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    response = create(client, headers, "Mạng máy tính", in_days(user, 55))
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "exam_date", "created_at"}
    assert (body["name"], body["exam_date"]) == ("Mạng máy tính", in_days(user, 55))
    uuid.UUID(body["id"])


def test_ac1_request_schema_has_exactly_name_and_exam_date() -> None:
    operation = app.openapi()["paths"]["/v1/subjects"]["post"]
    ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    schema = app.openapi()["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert set(schema["properties"]) == {"name", "exam_date"}
    assert set(schema["required"]) == {"name", "exam_date"}
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("field", ["user_id", "document", "id", "deleted_at"])
def test_ac1_b16_other_fields_are_refused(
    client: TestClient, db_session: Session, field: str
) -> None:
    user, headers = signed_in(db_session)
    body = {"name": "Mạng máy tính", "exam_date": in_days(user, 10), field: "x"}
    assert error_field(client.post("/v1/subjects", json=body, headers=headers)) == field


@pytest.mark.parametrize("missing", ["name", "exam_date"])
def test_ac1_both_fields_are_required(
    client: TestClient, db_session: Session, missing: str
) -> None:
    user, headers = signed_in(db_session)
    body = {"name": "Mạng máy tính", "exam_date": in_days(user, 10)}
    del body[missing]
    assert error_field(client.post("/v1/subjects", json=body, headers=headers)) == missing


@pytest.mark.parametrize("days", [0, -1, -400])
def test_ac2_exam_date_not_after_today_is_refused(
    client: TestClient, db_session: Session, days: int
) -> None:
    user, headers = signed_in(db_session)
    response = create(client, headers, "Mạng máy tính", in_days(user, days))
    assert (response.status_code, response.json()) == (422, {"detail": "exam_date_not_in_future"})
    assert client.get("/v1/subjects", headers=headers).json() == []


def test_ac2_tomorrow_is_accepted(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    assert create(client, headers, "Mạng máy tính", in_days(user, 1)).status_code == 201


@pytest.mark.parametrize("exam_date", ["15/12/2026", "2026-02-30", "", None, 20261215])
def test_malformed_exam_date_is_422(
    client: TestClient, db_session: Session, exam_date: object
) -> None:
    _, headers = signed_in(db_session)
    body = {"name": "Mạng máy tính", "exam_date": exam_date}
    assert error_field(client.post("/v1/subjects", json=body, headers=headers)) == "exam_date"


@pytest.mark.parametrize("name", ["", "   ", "\n\t", "x" * 201, None, 42])
def test_b12_blank_too_long_or_not_text_name_is_422(
    client: TestClient, db_session: Session, name: object
) -> None:
    user, headers = signed_in(db_session)
    body = {"name": name, "exam_date": in_days(user, 10)}
    assert error_field(client.post("/v1/subjects", json=body, headers=headers)) == "name"


def test_b12_name_of_200_characters_is_accepted(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    assert create(client, headers, "x" * 200, in_days(user, 10)).status_code == 201


def test_b12_name_is_stripped_and_composed(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    name = "  " + unicodedata.normalize("NFD", "Mạng máy tính") + " "
    assert create(client, headers, name, in_days(user, 10)).json()["name"] == "Mạng máy tính"


def test_b12_duplicate_names_are_allowed(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    for _ in range(2):
        assert create(client, headers, "Mạng máy tính", in_days(user, 10)).status_code == 201
    assert len(client.get("/v1/subjects", headers=headers).json()) == 2


def test_b17_create_writes_the_subject_and_its_one_exam(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng máy tính", in_days(user, 10)).json()["id"]
    exams = db_session.execute(
        text("SELECT exam_date, user_id FROM exam WHERE subject_id = :id"), {"id": subject_id}
    ).all()
    assert exams == [(today(user) + timedelta(days=10), user.id)]


# --- GET --------------------------------------------------------------------------------------


def test_get_lists_own_subjects_by_exam_date(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    _, other = signed_in(db_session)
    create(client, headers, "Mạng máy tính", in_days(user, 30))
    create(client, other, "Của người khác", in_days(user, 5))
    same_day = [f"Môn {n}" for n in range(5)]
    ids = [create(client, headers, name, in_days(user, 60)).json()["id"] for name in same_day]
    # now() is the transaction's start, the same for every row of this test: set them apart,
    # in an order that a sort on the (random) id alone would almost never give.
    for hours, subject_id in enumerate(reversed(ids), start=1):
        db_session.execute(
            text(
                "UPDATE subject SET created_at = now() - make_interval(hours => :h) WHERE id = :id"
            ),
            {"h": hours, "id": subject_id},
        )
    listed = client.get("/v1/subjects", headers=headers).json()
    # Soonest exam first; on the same day, the subject created first comes first.
    assert [s["name"] for s in listed] == ["Mạng máy tính", *same_day]


def test_get_without_subjects_is_an_empty_list(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    assert client.get("/v1/subjects", headers=headers).json() == []


def test_get_hides_deleted_subjects(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng máy tính", in_days(user, 10)).json()["id"]
    db_session.execute(
        text("UPDATE subject SET deleted_at = now() WHERE id = :id"), {"id": subject_id}
    )
    assert client.get("/v1/subjects", headers=headers).json() == []


def test_b14_me_has_subjects_after_creating_one(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    create(client, headers, "Mạng máy tính", in_days(user, 10))
    assert client.get("/v1/me", headers=headers).json()["has_subjects"] is True


# --- PATCH (AC2, B11) -------------------------------------------------------------------------


def patch(client: TestClient, headers: dict[str, str], subject_id: str, body: object) -> Any:
    return client.patch(f"/v1/subjects/{subject_id}", json=body, headers=headers)


@pytest.fixture
def owned(client: TestClient, db_session: Session) -> tuple[User, dict[str, str], str]:
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng máy tính", in_days(user, 30)).json()["id"]
    return user, headers, subject_id


def test_patch_changes_the_name(
    client: TestClient, owned: tuple[User, dict[str, str], str]
) -> None:
    user, headers, subject_id = owned
    response = patch(client, headers, subject_id, {"name": "  Mạng máy tính 2 "})
    assert response.status_code == 200
    assert (response.json()["name"], response.json()["exam_date"]) == (
        "Mạng máy tính 2",
        in_days(user, 30),
    )


def test_patch_changes_the_exam_date(
    client: TestClient, owned: tuple[User, dict[str, str], str]
) -> None:
    user, headers, subject_id = owned
    response = patch(client, headers, subject_id, {"exam_date": in_days(user, 40)})
    assert response.status_code == 200
    assert response.json()["exam_date"] == in_days(user, 40)
    listed = client.get("/v1/subjects", headers=headers).json()
    assert [s["exam_date"] for s in listed] == [in_days(user, 40)]


@pytest.mark.parametrize("days", [0, -1])
def test_ac2_patch_to_a_date_not_after_today_is_refused(
    client: TestClient, owned: tuple[User, dict[str, str], str], days: int
) -> None:
    user, headers, subject_id = owned
    response = patch(client, headers, subject_id, {"exam_date": in_days(user, days)})
    assert (response.status_code, response.json()) == (422, {"detail": "exam_date_not_in_future"})
    assert client.get("/v1/subjects", headers=headers).json()[0]["exam_date"] == in_days(user, 30)


def past_exam(db_session: Session, user: User, subject_id: str) -> str:
    """The stored exam date moved into the past, as it gets once the exam is over."""
    past = (today(user) - timedelta(days=3)).isoformat()
    db_session.execute(
        text("UPDATE exam SET exam_date = :day WHERE subject_id = :id"),
        {"day": past, "id": subject_id},
    )
    db_session.expire_all()
    return past


def test_b11_renaming_a_subject_whose_exam_is_over_is_allowed(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    user, headers, subject_id = owned
    past = past_exam(db_session, user, subject_id)
    response = patch(client, headers, subject_id, {"name": "Mạng (đã thi)"})
    assert response.status_code == 200
    assert response.json()["exam_date"] == past


def test_b11_sending_back_the_stored_past_date_is_allowed(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    # A form that sends every field must not get stuck once the exam is over.
    user, headers, subject_id = owned
    past = past_exam(db_session, user, subject_id)
    response = patch(client, headers, subject_id, {"name": "Mạng", "exam_date": past})
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "body"),
        ({"exam_date": None}, "body"),
        ({"name": None}, "body"),
        ({"name": "Mạng", "exam_date": None}, "body"),  # null is not "leave as is"
        ({"name": "   "}, "name"),
        ({"name": "x" * 201}, "name"),
        ({"name": "Mạng", "user_id": str(uuid.uuid4())}, "user_id"),
        ({"name": "Mạng", "deleted_at": None}, "deleted_at"),
    ],
)
def test_patch_bad_body_is_422(
    client: TestClient, owned: tuple[User, dict[str, str], str], body: object, field: str
) -> None:
    _, headers, subject_id = owned
    assert error_field(patch(client, headers, subject_id, body)) == field


def test_patch_unknown_subject_is_404(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    response = patch(client, headers, str(uuid.uuid4()), {"name": "Mạng"})
    assert (response.status_code, response.json()) == (404, {"detail": "subject_not_found"})


def test_patch_malformed_id_is_422(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    assert patch(client, headers, "not-a-uuid", {"name": "Mạng"}).status_code == 422


def test_patch_deleted_subject_is_404(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    _, headers, subject_id = owned
    db_session.execute(
        text("UPDATE subject SET deleted_at = now() WHERE id = :id"), {"id": subject_id}
    )
    assert patch(client, headers, subject_id, {"name": "Mạng"}).status_code == 404


# --- Isolation (ADR-0001) and unverified accounts (T1.9) ---------------------------------------


def test_adr_0001_bob_cannot_see_or_change_alices_subject(
    client: TestClient, db_session: Session, owned: tuple[User, dict[str, str], str]
) -> None:
    alice, alice_headers, subject_id = owned
    _, bob = signed_in(db_session)
    assert client.get("/v1/subjects", headers=bob).json() == []
    response = patch(client, bob, subject_id, {"name": "Của Bob", "exam_date": in_days(alice, 90)})
    assert (response.status_code, response.json()) == (404, {"detail": "subject_not_found"})
    listed = client.get("/v1/subjects", headers=alice_headers).json()
    assert [(s["name"], s["exam_date"]) for s in listed] == [("Mạng máy tính", in_days(alice, 30))]


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/v1/subjects"), ("POST", "/v1/subjects"), ("PATCH", f"/v1/subjects/{uuid.uuid4()}")],
)
def test_t1_9_unverified_account_is_refused(
    client: TestClient, db_session: Session, method: str, path: str
) -> None:
    _, headers = signed_in(db_session, verified=False)
    body = {"name": "Mạng máy tính", "exam_date": "2099-01-01"}
    response = client.request(method, path, json=body, headers=headers)
    assert (response.status_code, response.json()) == (403, {"detail": "email_not_verified"})


def test_not_signed_in_is_401(client: TestClient) -> None:
    assert client.get("/v1/subjects").status_code == 401
