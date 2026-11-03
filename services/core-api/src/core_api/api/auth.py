"""Account endpoints (ADR-0014, ADR-0019, ADR-0020).

Sign-up, resend and login never tell whether an address has an account (US-12 AC5): the same
answer, the same work (one argon2 hash), and what differs only happens later, in the email the
worker sends.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from core_api.api.deps import CurrentSession
from core_api.api.text import DbText, Email, LoginEmail
from core_api.config import get_settings
from core_api.db.models import User
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
from core_api.domain.auth.username import (
    UsernameRejectedError,
    normalize_username,
    validate_username,
)
from core_api.domain.email import normalize_email
from core_api.jobs.send_email import EmailKind, enqueue_email
from core_api.logging import set_user_id
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.email_token import EmailTokenRepository
from core_api.repositories.user import EmailTakenError, UsernameTakenError, UserRepository
from core_api.security.audit import security_event
from core_api.security.client_ip import client_ip
from core_api.security.rate_limit import (
    Cooldown,
    Hold,
    RateLimit,
    RateLimitedError,
    RateLimiter,
    get_rate_limiter,
)

DISPLAY_NAME_MAX = 60  # D7

router = APIRouter(prefix="/v1/auth")

# ADR-0014 limits sign-ups and resends per IP without a number. 10 an hour (owner's choice,
# 2026-10-20) leaves room for a shared network (a dormitory) and stops a script; revisit with
# the email provider's sending limits (T1.15).
REGISTER_PER_IP = RateLimit("register_ip", 10, timedelta(hours=1))
RESEND_PER_IP = RateLimit("resend_ip", 10, timedelta(hours=1))
# ADR-0014: emails to one address at least 60 s apart, whichever endpoint sends them.
EMAIL_COOLDOWN = Cooldown("email_address", timedelta(seconds=60))

RESET_PER_IP = RateLimit("reset_ip", 10, timedelta(hours=1))
CONFIRM_PER_IP = RateLimit("reset_confirm_ip", 30, timedelta(hours=1))

# ADR-0020 §2: failed logins, 5 per email+IP (one person mistyping does not lock others out) and
# 20 per email across IPs (a botnet trying one account), in 15-minute windows.
# T1.23: the "email" is whatever was typed in the one field, an email or a username, normalized.
# Someone who knows both names of one account gets a counter for each (the 20 cap still bounds
# guesses per name); no counter after the lookup: a lock that only exists for real accounts would
# reveal them.
LOGIN_PER_IDENTIFIER_IP = RateLimit("login_identifier_ip", 5, timedelta(minutes=15))
LOGIN_PER_IDENTIFIER = RateLimit("login_identifier", 20, timedelta(minutes=15))

# T1.23 (review P1): a username asked for with an address that already has an account is kept for
# as long as an unverified account would have been (jobs/purge_unverified.UNVERIFIED_LIFETIME),
# so "is this username free?" says nothing about whether an address has an account (AC5).
USERNAME_HOLD = Hold("username_hold", timedelta(days=7))

CHECK_EMAIL = {"status": "check_email"}

Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


class TokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # In the body, never the URL: request paths are logged and traced, bodies are not.
    token: str = Field(min_length=1, max_length=100)


class EmailBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email


class RegisterBody(EmailBody):
    # Longer than the 128-character rule, so too-long passwords get their reason (AC1).
    password: str = Field(max_length=1024)
    # Shape is checked in the handler, so each refusal gets its own reason (D2, D4).
    username: Annotated[DbText, Field(max_length=64)]
    display_name: Annotated[DbText, Field(max_length=200)] | None = None


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
    try:
        username = validate_username(normalize_username(body.username))
    except UsernameRejectedError as exc:
        raise HTTPException(status_code=422, detail=exc.problem.value) from None
    display_name = (body.display_name or "").strip() or None  # empty means none (D7)
    if display_name is not None and len(display_name) > DISPLAY_NAME_MAX:
        raise HTTPException(status_code=422, detail="display_name_too_long")
    limiter.enforce(REGISTER_PER_IP, client_ip(request, get_settings().web_token))
    users = UserRepository(session)
    # Whatever the email: a name that is taken is taken (a username is not a secret, D2).
    if users.username_taken(username) or limiter.is_reserved(USERNAME_HOLD, username):
        raise HTTPException(status_code=409, detail="username_taken")
    limiter.enforce_cooldown(EMAIL_COOLDOWN, email)
    password_hash = hash_password(body.password)  # hashed either way: same response time
    try:
        user = users.create(email, password_hash, username=username, display_name=display_name)
        kind = EmailKind.VERIFY_EMAIL
    except UsernameTakenError:  # lost a race with another sign-up for the same name
        raise HTTPException(status_code=409, detail="username_taken") from None
    except EmailTakenError:
        # Verified or not, the account keeps its password; the owner can reset it (ADR-0019).
        # The name asked for is kept as if the account had been made (review P1).
        limiter.reserve(USERNAME_HOLD, username)
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
    model_config = ConfigDict(extra="forbid")

    # An email or a username (D3), no other key. `email` is the old name of this field,
    # accepted until the web form sends `identifier` (T1.24), then removed.
    identifier: LoginEmail | None = None
    email: LoginEmail | None = None
    password: str = Field(max_length=1024)

    @model_validator(mode="after")
    def _one_name(self) -> "LoginBody":
        if self.identifier is None and self.email is None:
            raise ValueError("identifier is required")
        return self

    @property
    def typed(self) -> str:
        value = self.identifier if self.identifier is not None else self.email
        assert value is not None
        return value


class LoginResult(BaseModel):
    token: str
    expires_at: datetime  # the 90-day cap; web sets its cookie to end here (ADR-0020 §1)
    email_verified: bool


def _password_unchanged(session: DbSession, user: User) -> bool:
    """Lock the user's row and check the hash just verified is still the stored one.

    A reset may have committed while the password was being checked: the session this login
    creates would then outlive the reset's `revoke_all`, and a rehash would write the old
    password back over the new one. Under the lock, a reset either finished first (the hash
    differs: refuse, as for a wrong password) or waits for this login to commit, and then
    revokes its session too (ADR-0021).
    """
    checked = user.password_hash
    current = session.scalar(select(User.password_hash).where(User.id == user.id).with_for_update())
    return current is not None and current == checked


def login_pair_key(identifier: str, ip: str) -> str:
    return f"{identifier}|{ip}"


def _find_login_user(users: UserRepository, identifier: str) -> User | None:
    """An `@` means an email, anything else a username (D3); nothing else is a key."""
    if "@" in identifier:
        return users.get_by_email(identifier)
    return users.get_by_username(identifier)


@router.post("/login")
def login(body: LoginBody, request: Request, session: DbSession, limiter: Limiter) -> LoginResult:
    typed = body.typed.strip().lower()
    identifier = normalize_email(typed) if "@" in typed else normalize_username(typed)
    ip = client_ip(request, get_settings().web_token)
    # Counted before hashing, so a burst of requests cannot all slip past the limit while the
    # first ones are still hashing; a correct password gives its hits back below. Unknown
    # emails count too: a lock must not reveal which emails have accounts.
    hits = [
        limiter.hit(LOGIN_PER_IDENTIFIER_IP, login_pair_key(identifier, ip)),
        limiter.hit(LOGIN_PER_IDENTIFIER, identifier),
    ]
    refused = [hit for hit in hits if not hit.allowed]
    if refused:
        security_event("login_blocked", identifier=identifier, ip=ip)
        raise RateLimitedError(max(hit.retry_after_seconds for hit in refused))

    user = _find_login_user(UserRepository(session), identifier)
    if user is None or user.deleted_at is not None or user.password_hash is None:
        dummy_verify(body.password)  # the same work as a real check
        user = None
    elif not verify_password(user.password_hash, body.password) or not _password_unchanged(
        session, user
    ):
        user = None
    if user is None:
        security_event("login_failed", identifier=identifier, ip=ip)
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
    set_user_id(str(user.id))
    security_event("login_success", ip=ip)
    return LoginResult(
        token=token,
        expires_at=row.created_at + SESSION_MAX,
        email_verified=user.email_verified_at is not None,
    )


@router.post("/logout", status_code=204)
def logout(signed: CurrentSession, request: Request, session: DbSession) -> Response:
    AuthSessionRepository(session).revoke(signed.session, datetime.now(UTC))
    security_event("session_revoked", ip=client_ip(request, get_settings().web_token))
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
def logout_all(signed: CurrentSession, request: Request, session: DbSession) -> Response:
    """End every session of the user, this one included (ADR-0020 §3)."""
    AuthSessionRepository(session).revoke_all(signed.user.id, datetime.now(UTC))
    security_event("logout_all", ip=client_ip(request, get_settings().web_token))
    return Response(status_code=204)


@router.post("/password-reset", status_code=202)
def request_password_reset(
    body: EmailBody, request: Request, session: DbSession, limiter: Limiter
) -> dict[str, str]:
    """Email a one-hour reset link if the account exists; the same answer either way (AC5)."""
    ip = client_ip(request, get_settings().web_token)
    limiter.enforce(RESET_PER_IP, ip)
    email = normalize_email(body.email)
    limiter.enforce_cooldown(EMAIL_COOLDOWN, email)
    # Every address, known or not: the log is ours, and a run of these shows mailbox spam.
    security_event("password_reset_requested", email=email, ip=ip)
    user = UserRepository(session).get_by_email(email)
    if user is not None and user.deleted_at is None:
        enqueue_email(session, user.id, EmailKind.RESET_PASSWORD)
    return CHECK_EMAIL


def _reset_failed(ip: str) -> HTTPException:
    """Log a refused reset link (someone may be trying tokens) and build its single answer."""
    security_event("password_reset_failed", ip=ip)
    return HTTPException(status_code=400, detail="invalid_or_expired_token")


class ResetBody(TokenBody):
    password: str = Field(max_length=1024)


@router.post("/password-reset/confirm")
def confirm_password_reset(
    body: ResetBody, request: Request, session: DbSession, limiter: Limiter
) -> dict[str, str]:
    """Set a new password from a reset link (ADR-0021): the old password and every session end,
    the email counts as verified. Done in the request's transaction, with the token's use."""
    ip = client_ip(request, get_settings().web_token)
    limiter.enforce(CONFIRM_PER_IP, ip)
    now = datetime.now(UTC)
    tokens = EmailTokenRepository(session)
    users = UserRepository(session)
    owner = tokens.owner_of_live(body.token, TokenPurpose.RESET_PASSWORD, now)
    user = users.get(owner) if owner else None
    if user is None or user.deleted_at is not None:
        raise _reset_failed(ip)
    # The rules before the token is spent: a refused password leaves the link usable (§2).
    try:
        validate_password(body.password, email=user.email)
    except PasswordRejectedError as exc:
        raise HTTPException(status_code=422, detail=exc.problem.value) from None
    # consume decides, under the user's row lock: a second request with the same link, or one
    # with another of the user's links, finds it spent and gets the same 400.
    if tokens.consume(body.token, TokenPurpose.RESET_PASSWORD, now) != user.id:
        raise _reset_failed(ip)
    user.password_hash = hash_password(body.password)
    if user.email_verified_at is None:
        user.email_verified_at = now  # the link proved the mailbox is theirs (ADR-0021)
    AuthSessionRepository(session).revoke_all(user.id, now)
    set_user_id(str(user.id))
    security_event("password_reset", ip=ip)
    return {"status": "password_reset"}
