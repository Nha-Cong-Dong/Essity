"""One-time tokens for email links: verify an email, reset a password (ADR-0014).

The raw token goes into the link and nowhere else; the database keeps only its SHA-256. A
leaked database therefore holds no usable link. SHA-256 (not argon2) is enough here: the token
is 32 random bytes, far too many to guess, unlike a password.
"""

import hashlib
import secrets
from datetime import timedelta
from enum import StrEnum

TOKEN_BYTES = 32


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


VERIFY_EMAIL_TTL = timedelta(hours=24)  # US-12 AC2
RESET_PASSWORD_TTL = timedelta(hours=1)  # US-12 AC4 (T1.10)
TOKEN_TTL = {
    TokenPurpose.VERIFY_EMAIL: VERIFY_EMAIL_TTL,
    TokenPurpose.RESET_PASSWORD: RESET_PASSWORD_TTL,
}


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """Return (raw token for the link, hash for the database)."""
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    return raw, hash_token(raw)
