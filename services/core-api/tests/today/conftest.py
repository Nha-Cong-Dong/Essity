"""Fixed now for the /v1/today and review-session routes (R23), as in tests/subjects, and a stub
grader in place of ai-service (submitting grades at once, T2.13)."""

from collections.abc import Callable, Iterator
from datetime import datetime

import pytest

from clock import FROZEN_NOW
from core_api.api.deps import get_now
from core_api.api.ping import get_ai_client
from core_api.main import app
from grader_stub import Stub


@pytest.fixture(autouse=True)
def set_now() -> Iterator[Callable[[datetime], None]]:
    """The subjects routes read FROZEN_NOW, or the instant a test sets (R23)."""
    current = [FROZEN_NOW]
    app.dependency_overrides[get_now] = lambda: current[0]
    yield lambda instant: current.__setitem__(0, instant)
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture(autouse=True)
def stub() -> Iterator[Stub]:
    grader = Stub()
    app.dependency_overrides[get_ai_client] = lambda: grader
    yield grader
    app.dependency_overrides.pop(get_ai_client, None)
