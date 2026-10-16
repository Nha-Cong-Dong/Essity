"""One-time tokens for email links: verify an email, reset a password (ADR-0014).

The raw token goes into the link and nowhere else; the database keeps only its SHA-256. A
leaked database therefore holds no usable link. SHA-256 (not argon2) is enough here: the token
is 32 random bytes, far too many to guess, unlike a password.
"""

import hashlib
import secrets

TOKEN_BYTES = 32


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """Return (raw token for the link, hash for the database)."""
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    return raw, hash_token(raw)
