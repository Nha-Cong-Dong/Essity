"""Fixtures for the document routes (T4.5): a frozen "now" and a storage double."""

from collections.abc import Callable, Iterator
from datetime import datetime

import pytest

from clock import FROZEN_NOW
from core_api.api.deps import get_now, get_storage
from core_api.main import app
from fake_storage import FakeStorage


@pytest.fixture(autouse=True)
def set_now() -> Iterator[Callable[[datetime], None]]:
    """The document routes read FROZEN_NOW, or the instant a test sets (R23)."""
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
