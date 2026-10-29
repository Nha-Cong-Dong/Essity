"""Fixtures for the session routes (T4.12): a frozen "now", a storage double and an ai-service
double that answers what the test scripts."""

from collections.abc import Callable, Iterator
from datetime import datetime

import httpx2
import pytest

from clock import FROZEN_NOW
from core_api.api.deps import get_now, get_storage
from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import AiServiceClient
from core_api.config import get_settings
from core_api.main import app
from fake_storage import FakeStorage


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


@pytest.fixture(autouse=True)
def set_now() -> Iterator[Callable[[datetime], None]]:
    current = [FROZEN_NOW]
    app.dependency_overrides[get_now] = lambda: current[0]
    yield lambda instant: current.__setitem__(0, instant)
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def fake_storage() -> Iterator[FakeStorage]:
    storage = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: storage
    yield storage
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def fake_ai() -> Iterator[FakeAi]:
    ai = FakeAi()
    client = AiServiceClient.from_settings(get_settings(), httpx2.MockTransport(ai.handle))
    app.dependency_overrides[get_ai_client] = lambda: client
    yield ai
    app.dependency_overrides.pop(get_ai_client, None)
    client.close()
