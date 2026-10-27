"""T2.18: "Chấm sai" (`POST /v1/grades/{id}/override`) and "Bỏ câu này" (`POST /v1/questions/{id}/
drop`), US-09 AC2–AC4. Plan: no new design file; the choices are in the PR description.

Choices the spec leaves open (US-09 §9 #1, #2): the override sets every unit of the question to
the user's verdict and `overall` to the same; an override of a result already at that verdict
changes nothing; only the attempt's current grade can be overridden."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_t28_today_api import Space
from test_t213_attempts_api import opened, submit

from accounts import signed_in
from core_api.db.models import Grade, GradeUnit, MemoryState, Question, ReviewLog
from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
from core_api.domain.scheduling.rating import ReviewRating
from core_api.repositories.review import MemoryStateRepository

Headers = dict[str, str]


def grade_id_of(db_session: Session, attempt_id: str) -> str:
    """The attempt's newest grade, as the screen would hold it from the result."""
    grade = db_session.scalars(
        select(Grade).where(Grade.attempt_id == uuid.UUID(attempt_id)).order_by(Grade.seq.desc())
    ).first()
    assert grade is not None
    return str(grade.id)


def override(client: TestClient, headers: Headers, grade_id: str, verdict: str) -> Any:
    return client.post(
        f"/v1/grades/{grade_id}/override", json={"verdict": verdict}, headers=headers
    )


def states(db_session: Session, user_id: uuid.UUID) -> dict[uuid.UUID, State]:
    repo = MemoryStateRepository(db_session, user_id)
    return {row.unit_id: repo.state(row.unit_id) for row in repo.list()}  # type: ignore[misc]


def count(db_session: Session, model: Any, user_id: uuid.UUID) -> int:
    return db_session.scalar(select(func.count()).where(model.user_id == user_id)) or 0


# US-09 AC2. Red when: the schedule after "Chấm sai" differs from the one rebuilt from review_log,
# or the override does not move it at all.
def test_us09_ac2_after_override_the_schedule_equals_a_replay_from_scratch(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _, attempt_id = opened(client, db_session)
    submit(client, headers, attempt_id)
    before = states(db_session, space.user.id)
    response = override(client, headers, grade_id_of(db_session, attempt_id), "incorrect")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"]["overall"] == "incorrect" and body["grading"] == "graded"
    assert [u["verdict"] for u in body["result"]["units"]] == ["incorrect"]
    live = states(db_session, space.user.id)
    assert live != before
    MemoryStateRepository(db_session, space.user.id).delete_all()
    MemoryStateRepository(db_session, space.user.id).rebuild()
    assert states(db_session, space.user.id) == live


# US-09 AC2: the override is the attempt's current grade, so GET /v1/attempts shows it and
# /v1/today reads the moved schedule. Red when: the read paths still see the machine's grade.
def test_us09_ac2_the_attempt_and_today_show_the_override(
    client: TestClient, db_session: Session
) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    submit(client, headers, attempt_id)
    override(client, headers, grade_id_of(db_session, attempt_id), "incorrect")
    read = client.get(f"/v1/attempts/{attempt_id}", headers=headers).json()
    assert read["result"]["overall"] == "incorrect"
    assert client.get("/v1/today", headers=headers).status_code == 200


# US-09 AC3. Red when: the machine's grade row is changed or lost, or the new row does not say
# who made it.
def test_us09_ac3_the_machines_grade_stays_and_the_override_is_a_new_row(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _, attempt_id = opened(client, db_session)
    submit(client, headers, attempt_id)
    machine = db_session.scalars(select(Grade).where(Grade.user_id == space.user.id)).one()
    machine_snapshot = (machine.id, machine.source, machine.overall, machine.understanding)
    override(client, headers, str(machine.id), "incorrect")
    db_session.expire_all()
    rows = db_session.scalars(
        select(Grade).where(Grade.user_id == space.user.id).order_by(Grade.seq)
    ).all()
    assert [g.source for g in rows][1:] == ["user_override"]
    assert (rows[0].id, rows[0].source, rows[0].overall, rows[0].understanding) == machine_snapshot
    assert rows[1].overall == "incorrect" and rows[1].understanding is None
    assert count(db_session, GradeUnit, space.user.id) == 2
    # One review_log row per grade and unit; the replay reads only the newest grade's.
    logs = db_session.scalars(
        select(ReviewLog).where(ReviewLog.user_id == space.user.id).order_by(ReviewLog.seq)
    ).all()
    assert [log.rating for log in logs] == [ReviewRating.GOOD, ReviewRating.AGAIN]
    assert logs[0].reviewed_at == logs[1].reviewed_at  # the answer's time, not the override's


# US-09 AC3 and §9 #2. Red when: the user's second thought ("Thực ra tôi đúng" after "sai") or an
# override of "Không nhớ" cannot be recorded.
def test_us09_ac3_override_back_and_override_of_forgot(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _, attempt_id = opened(client, db_session)
    submit(client, headers, attempt_id, text="", forgot=True)
    forgot = grade_id_of(db_session, attempt_id)
    assert override(client, headers, forgot, "correct").json()["result"]["overall"] == "correct"
    second = grade_id_of(db_session, attempt_id)
    assert second != forgot
    assert override(client, headers, second, "incorrect").json()["result"]["overall"] == "incorrect"
    assert count(db_session, Grade, space.user.id) == 3
    MemoryStateRepository(db_session, space.user.id).delete_all()
    MemoryStateRepository(db_session, space.user.id).rebuild()
    assert count(db_session, MemoryState, space.user.id) == 1


# §9 #2 and idempotency. Red when: pressing the same verdict twice (a double tap, two tabs) writes
# another grade and another review.
def test_us09_override_to_the_verdict_it_already_has_changes_nothing(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _, attempt_id = opened(client, db_session)
    submit(client, headers, attempt_id)
    machine = grade_id_of(db_session, attempt_id)
    assert override(client, headers, machine, "correct").status_code == 200
    assert count(db_session, Grade, space.user.id) == 1
    assert override(client, headers, machine, "incorrect").status_code == 200
    again = override(client, headers, machine, "incorrect")
    assert again.status_code == 200 and again.json()["result"]["overall"] == "incorrect"
    assert count(db_session, Grade, space.user.id) == 2
    assert count(db_session, ReviewLog, space.user.id) == 2


# Red when: an old grade (not the attempt's newest) can be overridden into a branch of history.
def test_us09_only_the_current_grade_can_be_overridden(
    client: TestClient, db_session: Session
) -> None:
    space, headers, _, attempt_id = opened(client, db_session)
    submit(client, headers, attempt_id)
    machine = grade_id_of(db_session, attempt_id)
    override(client, headers, machine, "incorrect")
    stale = override(client, headers, machine, "correct")
    assert stale.status_code == 409 and stale.json()["detail"] == "grade_not_current"
    assert count(db_session, Grade, space.user.id) == 2


# US-09 §7, T2.18 "test cách ly". Red when: B can override A's grade, learns it exists, or
# moves A's schedule.
def test_t218_override_is_isolated_between_users(client: TestClient, db_session: Session) -> None:
    space, headers_a, _, attempt_id = opened(client, db_session)
    submit(client, headers_a, attempt_id)
    grade = grade_id_of(db_session, attempt_id)
    _, headers_b = signed_in(db_session)
    before = states(db_session, space.user.id)
    stranger = override(client, headers_b, grade, "incorrect")
    unknown = override(client, headers_b, str(uuid.uuid4()), "incorrect")
    assert stranger.status_code == unknown.status_code == 404
    assert stranger.json() == unknown.json()
    assert count(db_session, Grade, space.user.id) == 1
    assert states(db_session, space.user.id) == before


# Red when: a body with another verdict or an extra field is taken (mass assignment).
def test_t218_override_refuses_a_bad_body(client: TestClient, db_session: Session) -> None:
    _, headers, _, attempt_id = opened(client, db_session)
    submit(client, headers, attempt_id)
    grade = grade_id_of(db_session, attempt_id)
    for body in ({"verdict": "partial"}, {"verdict": "forgot"}, {}, {"verdict": "correct", "x": 1}):
        response = client.post(f"/v1/grades/{grade}/override", json=body, headers=headers)
        assert response.status_code == 422, body


# US-09 AC4. Red when: a dropped question comes back in today, in a new session, or stays in the
# session that was already open.
def test_us09_ac4_a_dropped_question_never_comes_again(
    client: TestClient, db_session: Session
) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    _, keep = space.question(subject, "TCP")
    _, dropped = space.question(subject, "UDP")
    started = client.post("/v1/review-sessions", json={}, headers=headers).json()
    assert started["total"] == 2
    response = client.post(f"/v1/questions/{dropped.id}/drop", headers=headers)
    assert response.status_code == 204
    # The open session no longer asks it, and its total shrinks.
    current = client.get(f"/v1/review-sessions/{started['id']}/current", headers=headers).json()
    assert current["question"]["id"] == str(keep.id) and current["total"] == 1
    db_session.expire_all()
    assert db_session.get(Question, dropped.id).status == "retired"  # type: ignore[union-attr]
    # A later day: neither today nor a session offers it.
    client.post(f"/v1/review-sessions/{started['id']}/stop", headers=headers)
    plan = client.get("/v1/today", headers=headers).json()
    assert plan["session"]["question_count"] == 1


# Red when: dropping twice answers an error the screen would show, or changes the row again.
def test_us09_ac4_dropping_twice_is_fine(client: TestClient, db_session: Session) -> None:
    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    _, question = space.question(space.subject())
    assert client.post(f"/v1/questions/{question.id}/drop", headers=headers).status_code == 204
    assert client.post(f"/v1/questions/{question.id}/drop", headers=headers).status_code == 204


# US-09 §7. Red when: B can retire A's question, or learns it exists.
def test_t218_drop_is_isolated_between_users(client: TestClient, db_session: Session) -> None:
    user, _ = signed_in(db_session)
    space = Space(db_session, user)
    _, question = space.question(space.subject())
    _, headers_b = signed_in(db_session)
    stranger = client.post(f"/v1/questions/{question.id}/drop", headers=headers_b)
    unknown = client.post(f"/v1/questions/{uuid.uuid4()}/drop", headers=headers_b)
    assert stranger.status_code == unknown.status_code == 404
    assert stranger.json() == unknown.json()
    db_session.expire_all()
    assert db_session.get(Question, question.id).status == "active"  # type: ignore[union-attr]


# Red when: a user not yet verified (or a subject deleted) reaches the routes anyway.
def test_t218_routes_need_a_verified_user(client: TestClient, db_session: Session) -> None:
    _, headers = signed_in(db_session, verified=False)
    assert client.post(f"/v1/questions/{uuid.uuid4()}/drop", headers=headers).status_code in (
        401,
        403,
    )
    response = client.post(
        f"/v1/grades/{uuid.uuid4()}/override", json={"verdict": "correct"}, headers=headers
    )
    assert response.status_code in (401, 403)


# US-09 (review T2-Y1). Red when: dropping a question of a deleted subject answers 204 and
# retires it, while override and skip answer 404 for the same case.
def test_t218_drop_of_a_deleted_subjects_question_is_404(
    client: TestClient, db_session: Session
) -> None:
    from clock import FROZEN_NOW
    from core_api.repositories.subject import SubjectRepository

    user, headers = signed_in(db_session)
    space = Space(db_session, user)
    subject = space.subject()
    _, question = space.question(subject)
    SubjectRepository(db_session, user.id).soft_delete(subject, FROZEN_NOW)
    db_session.flush()
    response = client.post(f"/v1/questions/{question.id}/drop", headers=headers)
    assert response.status_code == 404 and response.json() == {"detail": "question_not_found"}
    assert db_session.get(Question, question.id).status == "active"  # type: ignore[union-attr]
