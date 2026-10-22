"""T1.19: edge cases found by breaking the code on purpose (mutation testing by the tester).

Each test names the change in `src/` that turns it red.
"""

import itertools
import unicodedata
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
from core_api.domain.subjects import normalize_subject_name
from core_api.repositories.subject import SubjectRepository


def today(user: User) -> date:
    return learning_day(datetime.now(UTC), ZoneInfo(user.timezone), user.day_start_hour)


def in_days(user: User, days: int) -> str:
    return (today(user) + timedelta(days=days)).isoformat()


def create(client: TestClient, headers: dict[str, str], name: str, exam_date: object) -> Any:
    return client.post("/v1/subjects", json={"name": name, "exam_date": exam_date}, headers=headers)


# --- Name (B12) ---------------------------------------------------------------------------------


def test_b12_compatibility_characters_are_kept() -> None:
    """Red if NFC becomes NFKC: "ﬁ", "①" and full-width letters would be rewritten, and the
    student's own spelling of a subject name would change."""
    name = "Toán ① ﬁnance Ａ²"
    assert normalize_subject_name(name) == name


@pytest.mark.parametrize("name", [" ", "　 ", " \t \n "])
def test_b12_name_of_unicode_spaces_only_is_422(
    client: TestClient, db_session: Session, name: str
) -> None:
    """Red if the strip only removes ASCII spaces (`.strip(" ")`)."""
    user, headers = signed_in(db_session)
    response = create(client, headers, name, in_days(user, 10))
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "name"


def test_b12_length_counts_the_composed_name_not_the_typed_one(
    client: TestClient, db_session: Session
) -> None:
    """Red if the 200-character limit is checked before NFC: 200 letters typed with combining
    marks are 400 code points but a 200-character name (Unikey "Unicode tổ hợp")."""
    user, headers = signed_in(db_session)
    typed = unicodedata.normalize("NFD", "ạ" * 200)
    assert len(typed) == 400
    response = create(client, headers, typed, in_days(user, 10))
    assert response.status_code == 201
    assert response.json()["name"] == "ạ" * 200


def test_b12_length_does_not_count_the_stripped_spaces(
    client: TestClient, db_session: Session
) -> None:
    """Red if the limit is checked on the raw text: spaces around a 200-character name."""
    user, headers = signed_in(db_session)
    assert create(client, headers, "  " + "x" * 200 + "  ", in_days(user, 10)).status_code == 201
    assert create(client, headers, "x" * 201, in_days(user, 10)).status_code == 422


def test_b12_patch_name_is_normalized_like_create(client: TestClient, db_session: Session) -> None:
    """Red if PATCH skips the name validator (a second path to an unnormalized name)."""
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng", in_days(user, 10)).json()["id"]
    typed = "  " + unicodedata.normalize("NFD", "Hệ điều hành") + "\n"
    response = client.patch(f"/v1/subjects/{subject_id}", json={"name": typed}, headers=headers)
    assert response.json()["name"] == "Hệ điều hành"


def test_malformed_unicode_name_is_422_not_500(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session)
    body = b'{"name": "a\\ud800b", "exam_date": "2027-01-01"}'
    response = client.post(
        "/v1/subjects", content=body, headers={**headers, "content-type": "application/json"}
    )
    assert response.status_code == 422


def test_malformed_unicode_name_in_patch_is_422_not_500(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    subject_id = client.post(
        "/v1/subjects", json={"name": "Mạng", "exam_date": in_days(user, 30)}, headers=headers
    ).json()["id"]
    body = b'{"name": "a\\ud800b"}'
    response = client.patch(
        f"/v1/subjects/{subject_id}",
        content=body,
        headers={**headers, "content-type": "application/json"},
    )
    assert response.status_code == 422


# --- Exam date (AC2, B11, B21) ------------------------------------------------------------------


@pytest.mark.parametrize("stamp", [4102444800, 4102444800.0, 1893456000, 20991231])
def test_b21_a_number_is_not_read_as_a_timestamp(
    client: TestClient, db_session: Session, stamp: object
) -> None:
    """Red if the `BeforeValidator` that refuses non-strings is dropped: Pydantic would read
    4102444800 as the date 2100-01-01 and accept it as a future exam."""
    _, headers = signed_in(db_session)
    response = create(client, headers, "Mạng máy tính", stamp)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "exam_date"
    assert client.get("/v1/subjects", headers=headers).json() == []


def test_b21_patch_number_is_not_read_as_a_timestamp(
    client: TestClient, db_session: Session
) -> None:
    """Same rule on PATCH: the `ExamDate` type is shared, but a separate model could drift."""
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng", in_days(user, 10)).json()["id"]
    response = client.patch(
        f"/v1/subjects/{subject_id}", json={"exam_date": 4102444800}, headers=headers
    )
    assert response.status_code == 422
    assert client.get("/v1/subjects", headers=headers).json()[0]["exam_date"] == in_days(user, 10)


@pytest.mark.parametrize(
    ("exam_date", "status"),
    [("9999-12-31", 422), ("0001-01-01", 422), ("10000-01-01", 422), ("2099-13-01", 422)],
)
def test_exam_date_extremes_never_give_a_500(
    client: TestClient, db_session: Session, exam_date: str, status: int
) -> None:
    """The range of `date`: refused at both ends (the far one by plan K17's cap), never a crash."""
    _, headers = signed_in(db_session)
    assert create(client, headers, "Mạng máy tính", exam_date).status_code == status


@pytest.mark.parametrize("days", [1, 2, 365])
def test_ac2_patch_to_a_later_date_is_accepted(
    client: TestClient, db_session: Session, days: int
) -> None:
    """Red if PATCH refuses the first learning day after today (`<=` -> `<=` on days + 1)."""
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng", in_days(user, 30)).json()["id"]
    response = client.patch(
        f"/v1/subjects/{subject_id}", json={"exam_date": in_days(user, days)}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["exam_date"] == in_days(user, days)


def test_ac2_patch_with_a_name_and_a_past_date_changes_neither(
    client: TestClient, db_session: Session
) -> None:
    """Red if PATCH writes the name before it checks the date: the 422 would leave a rename
    behind (the test session does not roll back on an error, a real request does, B6)."""
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng", in_days(user, 30)).json()["id"]
    response = client.patch(
        f"/v1/subjects/{subject_id}",
        json={"name": "Đã đổi", "exam_date": in_days(user, -1)},
        headers=headers,
    )
    assert (response.status_code, response.json()) == (422, {"detail": "exam_date_not_in_future"})
    listed = client.get("/v1/subjects", headers=headers).json()
    assert [(s["name"], s["exam_date"]) for s in listed] == [("Mạng", in_days(user, 30))]


def test_b11_changing_a_past_date_to_another_past_date_is_refused(
    client: TestClient, db_session: Session
) -> None:
    """Red if "date changed" is read as "date present and the stored one is past": only the
    stored value itself is allowed back, any other past date is refused."""
    user, headers = signed_in(db_session)
    subject_id = create(client, headers, "Mạng", in_days(user, 30)).json()["id"]
    db_session.execute(
        text("UPDATE exam SET exam_date = :day WHERE subject_id = :id"),
        {"day": today(user) - timedelta(days=3), "id": subject_id},
    )
    db_session.expire_all()
    response = client.patch(
        f"/v1/subjects/{subject_id}", json={"exam_date": in_days(user, -2)}, headers=headers
    )
    assert (response.status_code, response.json()) == (422, {"detail": "exam_date_not_in_future"})


def test_ac2_a_user_in_another_time_zone_gets_their_own_learning_day(
    client: TestClient, db_session: Session
) -> None:
    """Red if the API validates against the server's (UTC) date instead of the user's
    time zone and day start: pick a zone whose learning day is a day ahead of UTC's."""
    user, headers = signed_in(db_session)
    user.timezone = "Pacific/Kiritimati"  # UTC+14
    user.day_start_hour = 0
    db_session.flush()
    kiritimati_today = today(user)
    assert create(client, headers, "Mạng", kiritimati_today.isoformat()).status_code == 422
    tomorrow = (kiritimati_today + timedelta(days=1)).isoformat()
    assert create(client, headers, "Mạng", tomorrow).status_code == 201


# --- Order and ownership in the repository (B17, B18) -------------------------------------------


@pytest.mark.parametrize("created_order", list(itertools.permutations(range(3))))
def test_list_with_exams_breaks_a_tie_on_the_exam_date_by_created_at(
    db_session: Session, two_users: tuple[User, User], created_order: tuple[int, ...]
) -> None:
    """Red if `Subject.created_at` leaves the ORDER BY (only the exam date): rows on the same
    day would come back in storage order. Subjects are stored in order 0, 1, 2 and given a
    `created_at` in every possible order, so storage order matches at most one case."""
    alice, _ = two_users
    subjects = SubjectRepository(db_session, alice.id)
    made = [subjects.create_with_exam(f"Môn {n}", date(2027, 1, 15))[0] for n in range(3)]
    db_session.flush()
    for n, subject in enumerate(made):
        db_session.execute(
            text("UPDATE subject SET created_at = :at WHERE id = :id"),
            {
                "at": datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=created_order[n]),
                "id": subject.id,
            },
        )
    db_session.expire_all()
    expected = [made[n].id for n in sorted(range(3), key=lambda n: created_order[n])]
    assert [s.id for s, _ in subjects.list_with_exams()] == expected


def test_has_any_counts_only_my_own_visible_subjects(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    """Red if `has_any` loses `user_id` (Bob's subject counts for Alice), the join with the
    exam, or the `deleted_at` filter."""
    alice, bob = two_users
    mine = SubjectRepository(db_session, alice.id)
    assert mine.has_any() is False
    SubjectRepository(db_session, bob.id).create_with_exam("Của Bob", date(2027, 1, 15))
    db_session.flush()
    assert mine.has_any() is False
    mine.create("Không có kỳ thi")
    db_session.flush()
    assert mine.has_any() is False
    gone, _ = mine.create_with_exam("Đã xóa", date(2027, 1, 15))
    db_session.flush()
    mine.soft_delete(gone.id)
    db_session.flush()
    assert mine.has_any() is False
    mine.create_with_exam("Còn", date(2027, 1, 15))
    db_session.flush()
    assert mine.has_any() is True


# --- Names Postgres cannot store, or that show as nothing (final review) --------------------


@pytest.mark.parametrize("name", ["a\u0000b", "Mạng\u0007", "a\u001fb"])
@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_control_characters_in_a_name_are_422_not_500(
    client: TestClient, db_session: Session, name: str, method: str
) -> None:
    """Red if `_name` lets control characters through: Postgres text refuses NUL (a 500)."""
    user, headers = signed_in(db_session)
    if method == "POST":
        response = client.post(
            "/v1/subjects", json={"name": name, "exam_date": in_days(user, 30)}, headers=headers
        )
    else:
        subject_id = client.post(
            "/v1/subjects", json={"name": "Mạng", "exam_date": in_days(user, 30)}, headers=headers
        ).json()["id"]
        response = client.patch(f"/v1/subjects/{subject_id}", json={"name": name}, headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "name"


@pytest.mark.parametrize("name", ["​", "​ ‍", "﻿", "⁠ "])
def test_a_name_that_shows_as_nothing_is_422(
    client: TestClient, db_session: Session, name: str
) -> None:
    """Red if a name of only invisible characters passes: the subject list would show a blank."""
    user, headers = signed_in(db_session)
    body = {"name": name, "exam_date": in_days(user, 30)}
    response = client.post("/v1/subjects", json=body, headers=headers)
    assert response.status_code == 422


def test_a_name_with_a_joiner_inside_visible_text_is_kept(
    client: TestClient, db_session: Session
) -> None:
    """Red if format characters are refused outright: they are only a problem when alone."""
    user, headers = signed_in(db_session)
    body = {"name": "Mạng‍máy", "exam_date": in_days(user, 30)}
    assert client.post("/v1/subjects", json=body, headers=headers).status_code == 201
