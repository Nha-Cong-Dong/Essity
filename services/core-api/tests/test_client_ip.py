"""T1.6: whose IP is this request from? Only web may tell core-api, and only with its token."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from core_api.security.client_ip import CLIENT_IP_HEADER, client_ip
from core_api.security.service_token import SERVICE_TOKEN_HEADER

WEB_TOKEN = "test-web-token-0123456789abcdef-0123"


def make_client(web_token: str | None) -> TestClient:
    app = FastAPI()

    @app.get("/ip")
    def ip(request: Request) -> dict[str, str]:
        return {"ip": client_ip(request, web_token)}

    _ = ip
    return TestClient(app, client=("198.51.100.7", 50000))


def ip_of(client: TestClient, headers: dict[str, str]) -> str:
    return client.get("/ip", headers=headers).json()["ip"]


def test_without_any_header_the_peer_address_is_used() -> None:
    assert ip_of(make_client(WEB_TOKEN), {}) == "198.51.100.7"


def test_ip_header_without_web_token_cannot_spoof() -> None:
    assert ip_of(make_client(WEB_TOKEN), {CLIENT_IP_HEADER: "203.0.113.9"}) == "198.51.100.7"


def test_ip_header_with_wrong_token_cannot_spoof() -> None:
    headers = {CLIENT_IP_HEADER: "203.0.113.9", SERVICE_TOKEN_HEADER: "wrong-token"}
    assert ip_of(make_client(WEB_TOKEN), headers) == "198.51.100.7"


def test_x_forwarded_for_is_never_trusted() -> None:
    headers = {"X-Forwarded-For": "203.0.113.9", SERVICE_TOKEN_HEADER: WEB_TOKEN}
    assert ip_of(make_client(WEB_TOKEN), headers) == "198.51.100.7"


@pytest.mark.parametrize("ip", ["203.0.113.9", "2001:db8::1"])
def test_web_with_its_token_passes_the_users_ip(ip: str) -> None:
    headers = {CLIENT_IP_HEADER: ip, SERVICE_TOKEN_HEADER: WEB_TOKEN}
    assert ip_of(make_client(WEB_TOKEN), headers) == ip


@pytest.mark.parametrize("bad", ["not-an-ip", "203.0.113.9, 10.0.0.1", "", "999.1.1.1"])
def test_malformed_ip_from_web_falls_back_to_the_peer(bad: str) -> None:
    headers = {CLIENT_IP_HEADER: bad, SERVICE_TOKEN_HEADER: WEB_TOKEN}
    assert ip_of(make_client(WEB_TOKEN), headers) == "198.51.100.7"


def test_without_a_configured_web_token_the_header_is_never_trusted() -> None:
    headers = {CLIENT_IP_HEADER: "203.0.113.9", SERVICE_TOKEN_HEADER: WEB_TOKEN}
    assert ip_of(make_client(None), headers) == "198.51.100.7"
