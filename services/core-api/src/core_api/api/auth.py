"""Account endpoints (ADR-0014, ADR-0019, ADR-0020).

Sign-up, resend and login never tell whether an address has an account (US-12 AC5): the same
answer, the same work (one argon2 hash), and what differs only happens later, in the email the
worker sends.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core_api.api.deps import CurrentSession
from core_api.config import get_settings
from core_api.db.session import DbSession
from core_api.domain.auth.passwords import (
    PasswordRejectedError,
    dummy_verify,
    hash_password,
    needs_rehash,
    validate_password,
    verify_password,
)
from core_api.domain.auth.sessions import SESSION_MAX
from core_api.domain.auth.tokens import TokenPurpose
from core_api.domain.email import normalize_email
from core_api.jobs.send_email import EmailKind, enqueue_email
from core_api.logging import user_id_var
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.email_token import EmailTokenRepository
from core_api.repositories.user import EmailTakenError, UserRepository
from core_api.security.audit import security_event
from core_api.security.client_ip import client_ip
from core_api.security.rate_limit import (
    Cooldown,
    RateLimit,
    RateLimitedError,
    RateLimiter,
    get_rate_limiter,
)

router = APIRouter(prefix="/v1/auth")

# ADR-0014 limits sign-ups and resends per IP without a number. 10 an hour (owner's choice,
# 2026-10-20) leaves room for a shared network (a dormitory) and stops a script; revisit with
# the email provider's sending limits (T1.15).
REGISTER_PER_IP = RateLimit("register_ip", 10, timedelta(hours=1))
RESEND_PER_IP = RateLimit("resend_ip", 10, timedelta(hours=1))
# ADR-0014: emails to one address at least 60 s apart, whichever endpoint sends them.
EMAIL_COOLDOWN = Cooldown("email_address", timedelta(seconds=60))

# ADR-0020 §2: failed logins, 5 per email+IP (one person mistyping does not lock others out) and
# 20 per email across IPs (a botnet trying one account), in 15-minute windows.
LOGIN_PER_EMAIL_IP = RateLimit("login_email_ip", 5, timedelta(minutes=15))
LOGIN_PER_EMAIL = RateLimit("login_email", 20, timedelta(minutes=15))

CHECK_EMAIL = {"status": "check_email"}

Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


class TokenBody(BaseModel):
    # In the body, never the URL: request paths are logged and traced, bodies are not.
    token: str = Field(min_length=1, max_length=100)


class EmailBody(BaseModel):
    # A light shape check; whether the address works is proven by the verification link.
    email: str = Field(max_length=320, pattern=r"^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$")


class RegisterBody(EmailBody):
    # Longer than the 128-character rule, so too-long passwords get their reason (AC1).
    password: str = Field(max_length=1024)


@router.post("/register", status_code=202)
def register(
    body: RegisterBody, request: Request, session: DbSession, limiter: Limiter
) -> dict[str, str]:
    email = normalize_email(body.email)
    # Password rules first, for every address: a refusal never depends on the address existing.
    # They cost nothing, so a refused password does not count against the IP's quota.
    try:
        validate_password(body.password, email=email)
    except PasswordRejectedError as exc:
        raise HTTPException(status_code=422, detail=exc.problem.value) from None
    limiter.enforce(REGISTER_PER_IP, client_ip(request, get_settings().web_token))
    limiter.enforce_cooldown(EMAIL_COOLDOWN, email)
    password_hash = hash_password(body.password)  # hashed either way: same response time
    users = UserRepository(session)
    try:
        user = users.create(email, password_hash)
        kind = EmailKind.VERIFY_EMAIL
    except EmailTakenError:
        # Verified or not, the account keeps its password; the owner can reset it (ADR-0019).
        user = users.get_by_email(email)
        kind = EmailKind.ACCOUNT_EXISTS
    if user is not None:
        enqueue_email(session, user.id, kind)
    return CHECK_EMAIL


@router.post("/verify-email/resend", status_code=202)
def resend_verification(
    body: EmailBody, request: Request, session: DbSession, limiter: Limiter
) -> dict[str, str]:
    # Per IP as well as per address: otherwise one script could mail every unverified
    # address it knows once a minute.
    limiter.enforce(RESEND_PER_IP, client_ip(request, get_settings().web_token))
    email = normalize_email(body.email)
    limiter.enforce_cooldown(EMAIL_COOLDOWN, email)
    user = UserRepository(session).get_by_email(email)
    if user is not None and user.email_verified_at is None and user.deleted_at is None:
        enqueue_email(session, user.id, EmailKind.VERIFY_EMAIL)
    return CHECK_EMAIL


@router.post("/verify-email")
def verify_email(body: TokenBody, session: DbSession) -> dict[str, str]:
    now = datetime.now(UTC)
    user_id = EmailTokenRepository(session).consume(body.token, TokenPurpose.VERIFY_EMAIL, now)
    user = UserRepository(session).get(user_id) if user_id else None
    if user is None or user.deleted_at is not None:
        # Unknown, used, expired and deleted-account links get the same answer (US-12 AC2).
        raise HTTPException(status_code=400, detail="invalid_or_expired_token")
    if user.email_verified_at is None:
        user.email_verified_at = now
    return {"status": "verified"}


class LoginBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class LoginResult(BaseModel):
    token: str
    expires_at: datetime  # the 90-day cap; web sets its cookie to end here (ADR-0020 §1)
    email_verified: bool


def login_pair_key(email: str, ip: str) -> str:
    return f"{email}|{ip}"


@router.post("/login")
def login(body: LoginBody, request: Request, session: DbSession, limiter: Limiter) -> LoginResult:
    email = normalize_email(body.email)
    ip = client_ip(request, get_settings().web_token)
    # Counted before hashing, so a burst of requests cannot all slip past the limit while the
    # first ones are still hashing; a correct password gives its hits back below. Unknown
    # emails count too: a lock must not reveal which emails have accounts.
    hits = [
        limiter.hit(LOGIN_PER_EMAIL_IP, login_pair_key(email, ip)),
        limiter.hit(LOGIN_PER_EMAIL, email),
    ]
    refused = [hit for hit in hits if not hit.allowed]
    if refused:
        security_event("login_blocked", email=email, ip=ip)
        raise RateLimitedError(max(hit.retry_after_seconds for hit in refused))

    user = UserRepository(session).get_by_email(email)
    if user is None or user.deleted_at is not None or user.password_hash is None:
        dummy_verify(body.password)  # the same work as a real check
        user = None
    elif not verify_password(user.password_hash, body.password):
        user = None
    if user is None:
        security_event("login_failed", email=email, ip=ip)
        raise HTTPException(status_code=401, detail="invalid_credentials")

    for hit in hits:  # only failures count; earlier failures stay counted (ADR-0020 §2)
        limiter.refund(hit)
    assert user.password_hash is not None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    now = datetime.now(UTC)
    token, row = AuthSessionRepository(session).create(
        user.id, now, request.headers.get("User-Agent")
    )
    user_id_var.set(str(user.id))
    security_event("login_success", ip=ip)
    return LoginResult(
        token=token,
        expires_at=row.created_at + SESSION_MAX,
        email_verified=user.email_verified_at is not None,
    )


@router.post("/logout", status_code=204)
def logout(signed: CurrentSession, session: DbSession) -> Response:
    AuthSessionRepository(session).revoke(signed.session, datetime.now(UTC))
    security_event("session_revoked")
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
def logout_all(signed: CurrentSession, session: DbSession) -> Response:
    """End every session of the user, this one included (ADR-0020 §3)."""
    AuthSessionRepository(session).revoke_all(signed.user.id, datetime.now(UTC))
    security_event("logout_all")
    return Response(status_code=204)
