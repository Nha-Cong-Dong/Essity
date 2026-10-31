"""Fixtures for the outline tests (T7.4): a storage double the routes and the handler use."""

from collections.abc import Iterator

import pytest

from core_api.api.deps import get_storage
from core_api.main import app
from fake_storage import FakeStorage


@pytest.fixture
def fake_storage() -> Iterator[FakeStorage]:
    storage = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: storage
    yield storage
    app.dependency_overrides.pop(get_storage, None)
