"""Password rules and hashing (ADR-0014, NIST SP 800-63B).

Rules: 8 to 128 characters, not a commonly used password, not the email itself. No forced
digits, capitals or symbols: they make passwords harder to remember, not harder to guess.

Passwords are Unicode-normalized (NFKC) before any check or hash, so the same password typed
on two keyboards (one code point "ệ", or "e" plus combining marks) is the same password.
Hashing is argon2id with argon2-cffi's defaults (RFC 9106 low-memory profile); never write
crypto by hand here.
"""

import secrets
import unicodedata
from enum import StrEnum
from functools import lru_cache
from importlib.resources import files

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 8
MAX_LENGTH = 128  # long enough for passphrases, short enough to bound hashing work

_hasher = PasswordHasher()


class PasswordProblem(StrEnum):
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    COMMON = "common"
    SAME_AS_EMAIL = "same_as_email"


class PasswordRejectedError(ValueError):
    def __init__(self, problem: PasswordProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


def _normalize(password: str) -> str:
    return unicodedata.normalize("NFKC", password)


@lru_cache
def _common_passwords() -> frozenset[str]:
    text = files("core_api.data").joinpath("common_passwords.txt").read_text("utf-8")
    return frozenset(line for line in text.splitlines() if line and not line.startswith("#"))


def validate_password(password: str, *, email: str | None = None) -> None:
    """Raise PasswordRejectedError if the password breaks a rule."""
    normalized = _normalize(password)
    if len(normalized) < MIN_LENGTH:
        raise PasswordRejectedError(PasswordProblem.TOO_SHORT)
    if len(normalized) > MAX_LENGTH:
        raise PasswordRejectedError(PasswordProblem.TOO_LONG)
    lowered = normalized.lower()
    if lowered in _common_passwords():
        raise PasswordRejectedError(PasswordProblem.COMMON)
    if email is not None:
        address = email.strip().lower()
        if lowered in {address, address.partition("@")[0]}:
            raise PasswordRejectedError(PasswordProblem.SAME_AS_EMAIL)


def hash_password(password: str) -> str:
    return _hasher.hash(_normalize(password))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, _normalize(password))
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with older parameters: rehash it at the next login."""
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(32))


def dummy_verify(password: str) -> bool:
    """Do the work of a real check, for an email that has no account (always False).

    Login then takes about as long whether or not the email exists, so response time does
    not reveal which emails have accounts (ADR-0014).
    """
    verify_password(_dummy_hash(), password)
    return False
