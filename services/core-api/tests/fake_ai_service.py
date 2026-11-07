"""Shared ai-service double (httpx2 MockTransport handler) for the session tests."""

import httpx2


class FakeAi:
    """What ai-service will answer, and the requests it got (bodies as sent)."""

    def __init__(self) -> None:
        self.answer: httpx2.Response | Exception = httpx2.Response(503, json={"code": "x"})
        self.requests: list[httpx2.Request] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer
