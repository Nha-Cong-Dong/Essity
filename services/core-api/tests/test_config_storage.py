"""Object storage settings (T4.5): fail closed outside local and test, like the others.

They are read from the `S3_*` variables the rest of the stack already uses (.env.example,
Compose's storage-init), not from a second `CORE_S3_*` set.
"""

import pytest
from pydantic import ValidationError

from core_api.config import GIB, MIB, Settings
from test_config import PRODUCTION, settings


def test_production_settings_with_storage_are_accepted() -> None:
    values = settings(**PRODUCTION)
    assert values.s3_endpoint.startswith("https://")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://r2.essity.example",  # file bytes in clear
        "https://127.0.0.1:9000",  # only works on one machine
        "https://localhost",
        "",
    ],
)
def test_outside_local_the_storage_endpoint_must_be_https_and_real(endpoint: str) -> None:
    with pytest.raises(ValidationError, match="s3_endpoint"):
        settings(**(PRODUCTION | {"s3_endpoint": endpoint}))


@pytest.mark.parametrize(
    "endpoint", ["http://files.essity.example", "https://127.0.0.1:9000", "files.essity.example"]
)
def test_outside_local_the_public_endpoint_must_be_https_and_real(endpoint: str) -> None:
    # The signed URL grants a write: over http anyone on the path could take it.
    with pytest.raises(ValidationError, match="s3_public_endpoint"):
        settings(**(PRODUCTION | {"s3_public_endpoint": endpoint}))


def test_outside_local_the_bucket_must_be_named() -> None:
    with pytest.raises(ValidationError, match="s3_bucket"):
        settings(**(PRODUCTION | {"s3_bucket": " "}))


def test_local_may_use_rustfs_over_http() -> None:
    values = settings(
        environment="local",
        s3_endpoint="http://storage:9000",
        s3_public_endpoint="http://localhost:9000",
    )
    assert values.s3_endpoint == "http://storage:9000"
    assert values.s3_public_endpoint == "http://localhost:9000"


@pytest.mark.parametrize("environment", ["local", "test"])
def test_an_empty_endpoint_is_refused_everywhere(environment: str) -> None:
    # boto3 reads "" as unset and would talk to Amazon S3 instead (review C5).
    with pytest.raises(ValidationError, match="s3_endpoint"):
        settings(environment=environment, s3_endpoint=" ")


def test_the_public_endpoint_defaults_to_the_endpoint() -> None:
    values = settings(environment="local", s3_endpoint="http://storage:9000")
    assert values.s3_public_endpoint == "http://storage:9000"
    unset = settings(environment="local", s3_endpoint="http://storage:9000", s3_public_endpoint="")
    assert unset.s3_public_endpoint == "http://storage:9000"  # Compose passes unset as ""


def test_settings_read_the_shared_s3_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_ENDPOINT", "http://storage:9000")
    monkeypatch.setenv("S3_BUCKET", "essity-files")
    values = Settings()  # pyright: ignore[reportCallIssue]
    assert values.s3_endpoint == "http://storage:9000"
    assert values.s3_bucket == "essity-files"


@pytest.mark.parametrize("variable", ["S3_ACCESS_KEY", "S3_SECRET_KEY"])
def test_the_storage_keys_are_required(monkeypatch: pytest.MonkeyPatch, variable: str) -> None:
    monkeypatch.delenv(variable)
    with pytest.raises(ValidationError, match=f"(?i){variable}"):
        Settings()  # pyright: ignore[reportCallIssue]


def test_the_storage_keys_are_never_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_ACCESS_KEY", "s3-access-that-must-never-be-printed")
    monkeypatch.setenv("S3_SECRET_KEY", "s3-secret-that-must-never-be-printed")
    with pytest.raises(ValidationError) as error:
        settings(environment="production")
    assert "never-be-printed" not in str(error.value)
    assert "never-be-printed" not in repr(settings(environment="local"))


def test_upload_urls_live_a_few_minutes_by_default() -> None:
    assert settings().s3_presign_seconds == 300


@pytest.mark.parametrize("seconds", ["59", "901"])
def test_upload_urls_live_one_to_fifteen_minutes(seconds: str) -> None:
    with pytest.raises(ValidationError, match="s3_presign_seconds"):
        settings(s3_presign_seconds=seconds)


def test_storage_calls_time_out_quickly_by_default() -> None:
    # Below web's 3 s timeout for core-api: confirm makes two calls.
    assert settings().s3_timeout_seconds == 1.0


def test_document_limits_default() -> None:
    values = settings()
    assert values.document_max_bytes == 100 * MIB
    assert values.document_quota_bytes == 500 * MIB
    assert values.storage_global_quota_bytes == 8 * GIB
    assert values.document_uploads_per_hour == 30
    assert values.document_cleanup_after_seconds == 3600


def test_abandoned_uploads_are_cleaned_only_after_their_url_is_dead() -> None:
    # A row deleted while its URL lives would let a PUT store a file nothing accounts for.
    with pytest.raises(ValidationError, match="document_cleanup_after_seconds"):
        settings(s3_presign_seconds="600", document_cleanup_after_seconds="1199")
    assert settings(s3_presign_seconds="600", document_cleanup_after_seconds="1200")
