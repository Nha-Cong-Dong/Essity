"""Service-to-service tokens, sent in X-Service-Token (never Authorization, kept for users)."""

import hmac

SERVICE_TOKEN_HEADER = "X-Service-Token"


def is_valid_service_token(presented: str | None, expected: str) -> bool:
    if presented is None:
        return False
    # Constant time, so response time does not reveal how much of the token matched.
    return hmac.compare_digest(presented.encode(), expected.encode())
