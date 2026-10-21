"""Security events (ADR-0013, ADR-0014): sign-ins, failures, locks, revocations.

One logger, `core_api.security`, so these lines can be kept and searched apart from the rest.
They never carry a password or a token. The email is masked by the log formatter. The IP is
kept only as a keyed hash: enough to see that failures come from one place, not enough to get
the address back without the key (a plain hash of an IPv4 address is reversed by trying all
2^32 of them).
"""

import hashlib
import hmac
import logging
import secrets
from functools import lru_cache

from core_api.config import get_settings

logger = logging.getLogger("core_api.security")

IP_HASH_LENGTH = 16  # hex characters


@lru_cache
def _process_key() -> bytes:
    """Locally, without a configured key: a random one per process."""
    return secrets.token_bytes(32)


def _key() -> bytes:
    configured = get_settings().log_hash_key
    return configured.get_secret_value().encode() if configured else _process_key()


def hash_ip(ip: str, key: bytes | None = None) -> str:
    digest = hmac.new(key or _key(), ip.encode(), hashlib.sha256).hexdigest()
    return digest[:IP_HASH_LENGTH]


def security_event(event: str, *, email: str | None = None, ip: str | None = None) -> None:
    """Log one security event. The user, when known, comes from `set_user_id`."""
    extra: dict[str, str] = {"event": event}
    if email is not None:
        extra["email"] = email
    if ip is not None:
        extra["ip_hash"] = hash_ip(ip)
    logger.info("security event", extra=extra)
