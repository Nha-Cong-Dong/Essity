"""T1.10: `POST /v1/auth/password-reset` and `POST /v1/auth/password-reset/confirm`.

Rules under test, each named in its test: US-12 AC1 (the new password follows the sign-up rules,
with the reason), AC4 (1-hour, one-time token; every session revoked; the email goes through the
job), AC5 (one answer whether the email exists or not), ADR-0019 (every unexpired link works
until one is used), ADR-0021 (a refused password leaves the token usable; a reset marks the
email verified; only the token's owner is touched), A10 (shared 60 s email cooldown, per-IP
limits), ADR-0013 (security event, no token or password in the logs).
"""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from core_api.api import auth
from core_api.db.models import User
from core_api.domain.auth.passwords import hash_password, verify_password
from core_api.domain.auth.tokens import RESET_PASSWORD_TTL, TokenPurpose
from core_api.repositories.email_token import EmailTokenRepository
from core_api.repositories.user import UserRepository
from core_api.security.audit import hash_ip
from ips import fresh_ip

RESET = "/v1/auth/password-reset"
CONFIRM = "/v1/auth/password-reset/confirm"
OLD = "ngựa vằn ăn cỏ buổi sáng"
NEW = "trâu già gặm cỏ non chiều"


def new_email() -> str:
    return f"reset-{uuid.uuid4().hex[:12]}@example.com"


def make_user(session: Session, *, verified: bool = True) -> User:
    user = UserRepository(session).create(new_email(), hash_password(OLD))
    if verified:
        user.email_verified_at = user.created_at
    session.flush()
    return user


def reset_token(session: Session, user: User, issued: datetime | None = None) -> str:
    raw = EmailTokenRepository(session).issue(user.id, TokenPurpose.RESET_PASSWORD, issued)
    session.flush()
    return raw


def confirm(client: TestClient, token: str, password: str = NEW) -> tuple[int, object]:
    response = client.post(CONFIRM, json={"token": token, "password": password})
    return response.status_code, response.json()


def sign_in(client: TestClient, user: User, password: str = OLD) -> str:
    response = client.post("/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200
    return str(response.json()["token"])


def me_status(client: TestClient, token: str) -> int:
    return client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code


def queued_emails(session: Session) -> list[dict[str, str]]:
    rows = session.execute(
        text("SELECT args FROM procrastinate_jobs WHERE task_name = 'send_email' ORDER BY id")
    ).scalars()
    return [row["payload"] for row in rows]


def other_ip() -> dict[str, str]:
    return {"X-Client-IP": fresh_ip("172.17")}


# --- Asking for a link (AC4, AC5) -------------------------------------------------------------


def test_ac5_reset_request_gives_one_answer_for_existing_and_unknown_email(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    known = client.post(RESET, json={"email": user.email})
    unknown = client.post(RESET, json={"email": new_email()})
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json())
    assert (known.status_code, known.json()) == (202, {"status": "check_email"})


def test_ac4_reset_enqueues_email_only_for_existing_account(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    deleted = make_user(db_session)
    deleted.deleted_at = datetime.now(UTC)
    db_session.flush()
    for email in (user.email, new_email(), deleted.email):
        assert client.post(RESET, json={"email": email}).status_code == 202
    assert queued_emails(db_session) == [{"user_id": str(user.id), "email": "reset_password"}]


def test_reset_request_works_for_an_unverified_account(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session, verified=False)
    assert client.post(RESET, json={"email": user.email}).status_code == 202
    assert [job["user_id"] for job in queued_emails(db_session)] == [str(user.id)]


def test_reset_shares_email_cooldown_and_is_limited_per_ip(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    assert client.post(RESET, json={"email": user.email}).status_code == 202
    again = client.post(RESET, json={"email": user.email}, headers=other_ip())
    assert again.status_code == 429  # same address, even from another IP
    resend = client.post(
        "/v1/auth/verify-email/resend", json={"email": user.email}, headers=other_ip()
    )
    assert resend.status_code == 429  # the cooldown is the address's, whichever endpoint
    for _ in range(auth.RESET_PER_IP.limit - 1):
        assert client.post(RESET, json={"email": new_email()}).status_code == 202
    assert client.post(RESET, json={"email": new_email()}).status_code == 429


# --- Using the link (AC4, AC1, ADR-0019, ADR-0021) --------------------------------------------


def test_reset_old_password_stops_working_new_one_does(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    assert confirm(client, reset_token(db_session, user)) == (200, {"status": "password_reset"})
    db_session.refresh(user)
    assert user.password_hash is not None
    assert verify_password(user.password_hash, NEW)
    assert not verify_password(user.password_hash, OLD)
    sign_in(client, user, NEW)


def test_ac4_reset_token_is_single_use(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    token = reset_token(db_session, user)
    assert confirm(client, token)[0] == 200
    assert confirm(client, token, "một mật khẩu khác hẳn") == (
        400,
        {"detail": "invalid_or_expired_token"},
    )


def test_ac4_reset_token_expires_after_1_hour(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    issued = datetime.now(UTC) - RESET_PASSWORD_TTL - timedelta(seconds=1)
    assert confirm(client, reset_token(db_session, user, issued)) == (
        400,
        {"detail": "invalid_or_expired_token"},
    )
    assert RESET_PASSWORD_TTL == timedelta(hours=1)


def test_ac4_verify_token_cannot_confirm_a_reset(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, verified=False)
    raw = EmailTokenRepository(db_session).issue(user.id, TokenPurpose.VERIFY_EMAIL)
    db_session.flush()
    assert confirm(client, raw)[0] == 400


def test_ac4_confirm_revokes_every_session(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    sessions = [sign_in(client, user) for _ in range(2)]
    assert confirm(client, reset_token(db_session, user))[0] == 200
    assert [me_status(client, token) for token in sessions] == [401, 401]


def test_reset_of_one_user_leaves_other_users_sessions(
    client: TestClient, db_session: Session
) -> None:
    alice, bob = make_user(db_session), make_user(db_session)
    bob_session = sign_in(client, bob)
    assert confirm(client, reset_token(db_session, alice))[0] == 200
    assert me_status(client, bob_session) == 200
    db_session.refresh(bob)
    assert bob.password_hash is not None and verify_password(bob.password_hash, OLD)


def test_ac1_confirm_applies_password_rules_and_a_refusal_keeps_the_token_usable(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    token = reset_token(db_session, user)
    assert confirm(client, token, "ngắn") == (422, {"detail": "too_short"})
    assert confirm(client, token, user.email) == (422, {"detail": "same_as_email"})
    assert confirm(client, token)[0] == 200


def test_second_reset_link_still_valid_until_one_used(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    first, second = reset_token(db_session, user), reset_token(db_session, user)
    assert confirm(client, second)[0] == 200
    assert confirm(client, first, "một mật khẩu khác hẳn")[0] == 400


def test_any_unexpired_reset_link_works_while_none_is_used(
    client: TestClient, db_session: Session
) -> None:
    user = make_user(db_session)
    first, _second = reset_token(db_session, user), reset_token(db_session, user)
    assert confirm(client, first)[0] == 200


def test_confirm_refuses_a_token_used_between_lookup_and_use(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two confirms of one link at once: the one that loses the race gets the same 400."""
    user = make_user(db_session)
    token = reset_token(db_session, user)
    lookup = EmailTokenRepository.owner_of_live

    def lookup_then_lose_the_race(
        self: EmailTokenRepository, raw: str, purpose: TokenPurpose, now: datetime
    ) -> uuid.UUID | None:
        owner = lookup(self, raw, purpose, now)
        EmailTokenRepository(db_session).consume(raw, purpose, now)  # the other request
        return owner

    monkeypatch.setattr(EmailTokenRepository, "owner_of_live", lookup_then_lose_the_race)
    assert confirm(client, token) == (400, {"detail": "invalid_or_expired_token"})
    db_session.refresh(user)
    assert user.password_hash is not None and verify_password(user.password_hash, OLD)


def test_reset_marks_unverified_email_as_verified(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session, verified=False)
    assert confirm(client, reset_token(db_session, user))[0] == 200
    db_session.refresh(user)
    assert user.email_verified_at is not None


def test_confirm_refuses_a_deleted_account(client: TestClient, db_session: Session) -> None:
    user = make_user(db_session)
    token = reset_token(db_session, user)
    user.deleted_at = datetime.now(UTC)
    db_session.flush()
    assert confirm(client, token) == (400, {"detail": "invalid_or_expired_token"})


def test_confirm_is_limited_per_ip(client: TestClient) -> None:
    for _ in range(auth.CONFIRM_PER_IP.limit):
        assert confirm(client, "not-a-real-token")[0] == 400
    assert confirm(client, "not-a-real-token")[0] == 429


# --- Logs (ADR-0013) --------------------------------------------------------------------------


def security_events(output: str) -> list[dict[str, object]]:
    lines = (json.loads(raw) for raw in output.splitlines() if raw.startswith("{"))
    return [line for line in lines if line.get("logger") == "core_api.security"]


def test_reset_events_logged_without_token(
    client: TestClient, db_session: Session, client_ip: str, log_output: Callable[[], str]
) -> None:
    """ADR-0013, PLAN T1.10: asking for a link (any address), a failed confirm and a reset are
    each a security event; neither token nor password reaches the log."""
    user = make_user(db_session)
    unknown = new_email()
    client.post(RESET, json={"email": unknown})
    bad = confirm(client, "not-a-real-token")
    token = reset_token(db_session, user)
    assert bad[0] == 400 and confirm(client, token)[0] == 200
    output = log_output()

    events = security_events(output)
    assert [line["event"] for line in events] == [
        "password_reset_requested",
        "password_reset_failed",
        "password_reset",
    ]
    for line in events:
        assert line["ip_hash"] == hash_ip(client_ip)
    assert events[2]["user_id"] == str(user.id)
    assert unknown not in output  # the address is masked
    for secret in (token, "not-a-real-token", NEW, OLD):
        assert secret not in output
