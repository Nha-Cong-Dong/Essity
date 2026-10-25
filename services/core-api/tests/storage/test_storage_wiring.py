"""The app builds its object storage from the settings at startup (T4.5)."""

import pytest
from fastapi.testclient import TestClient

from core_api.clients.storage import S3Storage
from core_api.config import get_settings
from core_api.main import app


def test_the_app_starts_with_a_storage_from_settings() -> None:
    with TestClient(app):
        assert isinstance(app.state.storage, S3Storage)


def test_storage_from_settings_reaches_the_store(
    monkeypatch: pytest.MonkeyPatch, s3_bucket: str, object_key: str
) -> None:
    monkeypatch.setenv("S3_BUCKET", s3_bucket)
    get_settings.cache_clear()

    storage = S3Storage.from_settings(get_settings())

    assert storage.head(object_key) is None  # answered, with our keys: not an error
