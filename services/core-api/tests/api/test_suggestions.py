"""T7.10b (US-15): `GET /v1/suggestions` and `GET /v1/subjects/{id}/suggestion` over the real
tables. The ranking rules are in tests/domain/test_suggest.py; here the reads, the API shape,
isolation and the unverified user."""

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from clock import FROZEN_NOW
from core_api.db.models import Document, Subject, UnitEdge, UnitSection, User
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import DraftRepository
from v2_rows import (
    make_document,
    make_section,
    make_study_session,
    make_subject,
    make_unit,
)

TODAY = FROZEN_NOW.date()  # the default user timezone is UTC: still the 22nd
BANNED = re.compile(r"\b(phải|cần|kịp|trễ)\b", re.IGNORECASE)


def headers_of(session: Session, user: User) -> dict[str, str]:
    user.email_verified_at = FROZEN_NOW
    token, _ = AuthSessionRepository(session).create(user.id, datetime.now(UTC))
    session.flush()
    return {"Authorization": f"Bearer {token}"}


def subject_with(
    session: Session, user: User, name: str, leaves: list[dict[str, Any]], days: int | None = 20
) -> tuple[Subject, Document, list[Any]]:
    subject = make_subject(session, user, name)
    if days is not None:
        SubjectRepository(session, user.id).update(subject.id, exam_date=TODAY + timedelta(days))
    doc = make_document(session, user, subject, sha=uuid.uuid4().hex + uuid.uuid4().hex)
    sections = [
        make_section(session, user, doc, ord=i, title=f"Mục {i + 1}", **extra)
        for i, extra in enumerate(leaves)
    ]
    return subject, doc, sections


def get(client: TestClient, headers: dict[str, str], path: str = "/v1/suggestions") -> Any:
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in cast(dict[str, Any], value).values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in cast(list[Any], value) for s in strings(v)]
    return []


def log_saved(session: Session, user: User, subject: Subject, day: Any) -> None:
    row = make_study_session(session, user, subject)
    DraftRepository(session, user.id).ledger_add(
        subject_id=subject.id, session_id=row.id, learning_day=day, section_id=None, count=1
    )
    session.flush()


# AC1, AC2: at most two subjects, each with its next leaf and a reason.
def test_ac1_ac2_top_two_with_next_leaf_and_reason(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    s1, _, secs = subject_with(db_session, alice, "A", [{"weight": 10}, {"weight": 10}], days=5)
    subject_with(db_session, alice, "B", [{"weight": 10}], days=30)
    subject_with(db_session, alice, "C", [{"weight": 10}], days=60)
    secs[0].studied_weight = 10  # leaf 1 done, leaf 2 next
    db_session.flush()
    body = get(client, h)
    assert len(body["suggestions"]) == 2
    first = body["suggestions"][0]
    assert first["subject_id"] == str(s1.id)
    assert first["section_title"] == "Mục 2"
    assert first["kind"] == "next_leaf"
    assert first["reason"]
    assert first["pace"]["text"] == "còn 1 mục (10 trang), 5 ngày"
    assert body["empty"] is None


# AC2: holes left by studying ahead are suggested again; a partly studied leaf says what is left.
def test_ac2_hole_and_partial(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    leaves: list[dict[str, Any]] = [{"weight": 10}] * 3
    s, _, secs = subject_with(db_session, alice, "A", leaves)
    secs[2].studied_weight = 10  # studied ahead
    secs[0].studied_weight = 4
    db_session.flush()
    one = get(client, h, f"/v1/subjects/{s.id}/suggestion")["suggestion"]
    assert one["section_id"] == str(secs[0].id)
    assert one["partial"] is True
    assert one["remaining"] == 6
    secs[0].studied_weight = 10
    db_session.flush()
    one = get(client, h, f"/v1/subjects/{s.id}/suggestion")["suggestion"]
    assert one["section_id"] == str(secs[1].id)  # the hole
    assert one["partial"] is False


def test_ac2_nested_outline_is_walked_depth_first(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    s, doc, secs = subject_with(db_session, alice, "A", [{}, {}])
    child = make_section(db_session, alice, doc, ord=0, title="1.1", parent_id=secs[0].id)
    one = get(client, h, f"/v1/subjects/{s.id}/suggestion")["suggestion"]
    assert one["section_id"] == str(child.id)  # the parent is not a leaf


# AC2 + T9.9: an active prerequisite edge pulls its target first, at any position.
def test_ac2_prerequisite_edge_comes_first(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    s, _, secs = subject_with(db_session, alice, "A", [{}, {}, {}])
    u1, u3 = make_unit(db_session, alice, s), make_unit(db_session, alice, s)
    for unit, sec in ((u1, secs[0]), (u3, secs[2])):
        db_session.add(
            UnitSection(user_id=alice.id, subject_id=s.id, unit_id=unit.id, section_id=sec.id)
        )
    db_session.add(
        UnitEdge(
            user_id=alice.id,
            subject_id=s.id,
            src_unit_id=u1.id,  # leaf 1 needs leaf 3 first
            dst_unit_id=u3.id,
            kind="prerequisite",
            origin="user",
            status="active",
        )
    )
    db_session.flush()
    one = get(client, h, f"/v1/subjects/{s.id}/suggestion")["suggestion"]
    assert one["section_id"] == str(secs[2].id)


# AC3: tighter subject first; no exam date last; exam passed is not suggested.
def test_ac3_ranking_no_date_last_and_past_exam_dropped(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    nodate, *_ = subject_with(db_session, alice, "none", [{"weight": 99}], days=None)
    soon, *_ = subject_with(db_session, alice, "soon", [{"weight": 10}], days=2)
    past, *_ = subject_with(db_session, alice, "past", [{"weight": 99}], days=-3)
    body = get(client, h)
    assert [s["subject_id"] for s in body["suggestions"]] == [str(soon.id), str(nodate.id)]
    assert str(past.id) not in strings(body)


# AC3: a tie goes to the subject studied longest ago (ledger).
def test_ac3_tie_goes_to_longest_unstudied_per_ledger(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    a, *_ = subject_with(db_session, alice, "A", [{"weight": 10}], days=10)
    b, *_ = subject_with(db_session, alice, "B", [{"weight": 10}], days=10)
    c, *_ = subject_with(db_session, alice, "C", [{"weight": 10}], days=10)
    log_saved(db_session, alice, a, TODAY - timedelta(days=1))
    log_saved(db_session, alice, b, TODAY - timedelta(days=5))
    ids = [s["subject_id"] for s in get(client, h)["suggestions"]]
    assert ids == [str(c.id), str(b.id)]  # never studied, then the oldest


# AC4: not stored: a missed day changes nothing, a changed state changes the answer.
def test_ac4_recomputed_every_time(
    client: TestClient,
    db_session: Session,
    two_users: tuple[User, User],
    set_now: Callable[[datetime], None],
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    _, _, secs = subject_with(db_session, alice, "A", [{}, {}], days=30)
    first = get(client, h)["suggestions"][0]["section_id"]
    set_now(FROZEN_NOW + timedelta(days=4))  # four days with nothing studied
    assert get(client, h)["suggestions"][0]["section_id"] == first
    secs[0].studied_weight = 1
    db_session.flush()
    assert get(client, h)["suggestions"][0]["section_id"] == str(secs[1].id)


# AC5: numbers only; no banned word in any string, in the body or the empty state.
def test_ac5_no_pressure_wording_anywhere(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    subject_with(db_session, alice, "A", [{"weight": 86}], days=20)
    subject_with(db_session, alice, "B", [{"weight": 5, "studied_weight": 5}], days=9)
    subject_with(db_session, alice, "C", [], days=9)
    body = get(client, h)
    assert any("còn 1 mục (86 trang), 20 ngày" in t for t in strings(body))
    assert not [t for t in strings(body) if BANNED.search(t)]


# AC7, AC11: edge cases never leave the screen blank and always point to review and practice.
def test_ac7_ac11_empty_reasons(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    body = get(client, h)
    assert body["empty"]["reason"] == "no_subjects"
    assert body["empty"]["links"] == ["review", "practice"]
    subject_with(db_session, alice, "Past", [{}], days=-2)
    assert get(client, h)["empty"]["reason"] == "nothing_open"
    subject_with(db_session, alice, "Free", [], days=10)
    body = get(client, h)
    assert body["empty"]["reason"] == "no_syllabus"
    assert body["finished"][0]["kind"] == "free_session"
    assert not [t for t in strings(body) if BANNED.search(t)]


def test_ac7_ac11_all_studied_and_all_excluded_go_to_review_practice(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    done, *_ = subject_with(db_session, alice, "Done", [{"weight": 3, "studied_weight": 3}])
    skip, *_ = subject_with(db_session, alice, "Skip", [{"excluded": True}])
    body = get(client, h)
    assert body["suggestions"] == []
    assert {f["subject_id"] for f in body["finished"]} == {str(done.id), str(skip.id)}
    assert all(f["kind"] == "review_practice" for f in body["finished"])
    assert body["empty"]["reason"] == "all_studied"
    assert not [t for t in strings(body) if BANNED.search(t)]


# AC6 (API part): the button's endpoint answers for a subject outside the top two.
def test_ac6_button_for_subject_outside_top_two(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    subject_with(db_session, alice, "1", [{}], days=1)
    subject_with(db_session, alice, "2", [{}], days=2)
    third, *_ = subject_with(db_session, alice, "3", [{}], days=3)
    assert str(third.id) not in [s["subject_id"] for s in get(client, h)["suggestions"]]
    one = get(client, h, f"/v1/subjects/{third.id}/suggestion")["suggestion"]
    assert one["kind"] == "next_leaf" and one["section_title"] == "Mục 1"


# AC8: Save's ledger row is what the next suggestion reads.
def test_ac8_ledger_row_changes_the_next_suggestion(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    subjects = [
        subject_with(db_session, alice, n, [{"weight": 10}], days=10)[0] for n in ("A", "B", "C")
    ]
    shown = [s["subject_id"] for s in get(client, h)["suggestions"]]
    assert len(shown) == 2
    for subject in subjects:
        if str(subject.id) in shown:
            log_saved(db_session, alice, subject, TODAY)
    left = next(str(s.id) for s in subjects if str(s.id) not in shown)
    assert get(client, h)["suggestions"][0]["subject_id"] == left


# Isolation and the unverified user.
def test_isolation_other_users_data_is_never_seen(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    s, *_ = subject_with(db_session, alice, "A", [{}])
    hb = headers_of(db_session, bob)
    body = get(client, hb)
    assert body["suggestions"] == [] and body["empty"]["reason"] == "no_subjects"
    assert str(s.id) not in strings(body)
    response = client.get(f"/v1/subjects/{s.id}/suggestion", headers=hb)
    assert response.status_code == 404


def test_unverified_user_is_rejected(
    client: TestClient, db_session: Session, unverified_user: User
) -> None:
    token, _ = AuthSessionRepository(db_session).create(unverified_user.id, datetime.now(UTC))
    h = {"Authorization": f"Bearer {token}"}
    for path in ("/v1/suggestions", f"/v1/subjects/{uuid.uuid4()}/suggestion"):
        response = client.get(path, headers=h)
        assert response.status_code == 403
        assert response.json()["detail"] == "email_not_verified"


# AC10: the service reads the user's timezone and day_start_hour (03:30 in Ho Chi Minh City).
def test_ac10_user_timezone_and_day_start_hour_shift_the_learning_day(
    client: TestClient, db_session: Session, two_users: tuple[User, User]
) -> None:
    alice = two_users[0]
    h = headers_of(db_session, alice)
    s, *_ = subject_with(db_session, alice, "A", [{"weight": 10}], days=5)  # exam TODAY + 5
    alice.timezone = "Asia/Ho_Chi_Minh"
    alice.day_start_hour = 4  # 03:30 is before the cut: still the 22nd
    db_session.flush()
    body = get(client, h)
    assert body["today"] == str(TODAY)
    assert body["suggestions"][0]["pace"]["days_left"] == 5
    alice.day_start_hour = 0  # the 23rd already began
    db_session.flush()
    body = get(client, h)
    assert body["today"] == str(TODAY + timedelta(days=1))
    assert body["suggestions"][0]["pace"]["days_left"] == 4
    one = get(client, h, f"/v1/subjects/{s.id}/suggestion")
    assert one["today"] == str(TODAY + timedelta(days=1))
