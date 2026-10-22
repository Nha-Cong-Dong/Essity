from collections.abc import Callable, Iterator
from datetime import datetime

import pytest

from clock import FROZEN_NOW
from core_api.api.deps import get_now
from core_api.main import app


@pytest.fixture(autouse=True)
def set_now() -> Iterator[Callable[[datetime], None]]:
    """The subjects routes read FROZEN_NOW, or the instant a test sets (R23)."""
    current = [FROZEN_NOW]
    app.dependency_overrides[get_now] = lambda: current[0]
    yield lambda instant: current.__setitem__(0, instant)
    app.dependency_overrides.pop(get_now, None)
