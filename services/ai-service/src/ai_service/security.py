import hmac
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from ai_service.config import get_settings

SERVICE_TOKEN_HEADER = "X-Service-Token"
PUBLIC_PATHS = frozenset({"/healthz"})


def is_valid_service_token(presented: str | None, expected: str) -> bool:
    if presented is None:
        return False
    # Constant-time comparison so response time does not leak how much of the token matched.
    return hmac.compare_digest(presented.encode(), expected.encode())


async def require_service_token(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.url.path not in PUBLIC_PATHS:
        expected = get_settings().service_token.get_secret_value()
        if not is_valid_service_token(request.headers.get(SERVICE_TOKEN_HEADER), expected):
            return JSONResponse({"detail": "Invalid service token"}, status_code=401)
    return await call_next(request)
