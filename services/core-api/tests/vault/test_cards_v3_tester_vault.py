"""CARDS-V3 tester edges: the session result the screen polls, and the draft review that is gone."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import StudySession, Submission, User
from core_api.repositories.auth_session import AuthSessionRepository
from v2_rows import make_subject, make_unit


def _study(db: Session) -> tuple[User, dict[str, str], StudySession]:
    user, headers = signed_in(db)
    subject = make_subject(db, user)
    study = StudySession(
        user_id=user.id,
        subject_id=subject.id,
        description_raw="học @Giáo trình phần 1.1.1",
        extraction="proposed",
        status="confirmed",
        confirmed_at=datetime.now(UTC),
        studied_on=datetime.now(UTC).date(),
        learning_day=datetime.now(UTC).date(),
    )
    db.add(study)
    db.flush()
    make_unit(db, user, subject, status="canonical", session_id=study.id, title="Phép thử")
    make_unit(db, user, subject, status="retired", session_id=study.id, title="Đã xóa")
    db.commit()
    return user, headers, study


def test_result_reports_the_latest_submission_and_counts_only_vault_cards(
    client: TestClient, db_session: Session
) -> None:
    # Red when: the screen reads the first (failed) submission of a retried session, so it shows
    # a failure after the retry succeeded; or a card the learner deleted is counted as added.
    user, headers, study = _study(db_session)
    first = datetime.now(UTC) - timedelta(hours=1)
    db_session.add_all(
        [
            Submission(
                user_id=user.id,
                session_id=study.id,
                status="failed",
                created_at=first,
                finished_at=first,
            ),
            Submission(
                user_id=user.id,
                session_id=study.id,
                status="done",
                created_at=first + timedelta(minutes=30),
                finished_at=first + timedelta(minutes=31),
            ),
        ]
    )
    db_session.commit()
    body = client.get(f"/v1/vault/sessions/{study.id}/result", headers=headers).json()
    assert body["submission_status"] == "done"
    assert body["cards"] == 1


def test_result_refuses_an_unverified_user(
    client: TestClient, db_session: Session, unverified_user: User
) -> None:
    # Red when: the result endpoint drops VerifiedUser and answers a learner whose email is not
    # verified.
    token, _ = AuthSessionRepository(db_session).create(unverified_user.id, datetime.now(UTC))
    response = client.get(
        f"/v1/vault/sessions/{uuid.uuid4()}/result", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_the_draft_review_routes_are_gone(client: TestClient, db_session: Session) -> None:
    # Red when: any route of the old draft review screen still answers (cards go straight to the
    # Kho; a draft API left behind would let a client keep cards out of the vault).
    _, headers, study = _study(db_session)
    unit = uuid.uuid4()
    calls = [
        ("GET", f"/v1/sessions/{study.id}/drafts"),
        ("POST", f"/v1/sessions/{study.id}/drafts"),
        ("POST", f"/v1/sessions/{study.id}/drafts/merge"),
        ("POST", f"/v1/sessions/{study.id}/drafts/save"),
        ("GET", f"/v1/drafts/{unit}"),
        ("PATCH", f"/v1/drafts/{unit}"),
        ("DELETE", f"/v1/drafts/{unit}"),
        ("POST", f"/v1/drafts/{unit}/undo"),
        ("POST", f"/v1/drafts/{unit}/split"),
    ]
    for method, path in calls:
        response = client.request(method, path, headers=headers, json={})
        assert response.status_code in (404, 405), (method, path, response.status_code)
