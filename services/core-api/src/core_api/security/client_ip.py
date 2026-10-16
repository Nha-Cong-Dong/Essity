"""The user's IP address, for per-IP rate limits (T1.6).

core-api is only reached through web (ARCH §3), so the TCP peer is web, not the user. web
passes the user's address in X-Client-IP, and core-api believes it only when the request
also carries web's service token. Anyone else could send any address and dodge every per-IP
limit, which is also why X-Forwarded-For is ignored.
"""

import ipaddress

from fastapi import Request
from pydantic import SecretStr

from core_api.security.service_token import SERVICE_TOKEN_HEADER, is_valid_service_token

CLIENT_IP_HEADER = "X-Client-IP"
UNKNOWN = "unknown"


def client_ip(request: Request, web_token: SecretStr | str | None) -> str:
    peer = request.client.host if request.client else UNKNOWN
    if web_token is None:
        return peer
    expected = web_token.get_secret_value() if isinstance(web_token, SecretStr) else web_token
    if not is_valid_service_token(request.headers.get(SERVICE_TOKEN_HEADER), expected):
        return peer
    claimed = request.headers.get(CLIENT_IP_HEADER, "").strip()
    try:
        return str(ipaddress.ip_address(claimed))
    except ValueError:
        return peer
