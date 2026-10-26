import ipaddress
from email.utils import parseaddr
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments where defaults pointing at localhost are fine.
DEV_ENVIRONMENTS = frozenset({"local", "test"})
LOCAL_WEB_BASE_URL = "http://localhost:3000"

Environment = Literal["local", "test", "staging", "production"]

MIB = 1024**2
GIB = 1024**3


def _is_dev(info: ValidationInfo) -> bool:
    # A missing or unknown environment is not in info.data: the rules then run as production's
    # (plan D1), so a typo fails closed instead of starting with local defaults.
    return info.data.get("environment") in DEV_ENVIRONMENTS


def _is_loopback(host: str) -> bool:
    """localhost, 127.0.0.0/8, ::1 or 0.0.0.0: a value that only works on one machine."""
    host = host.strip("[]").lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _is_remote_https(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return url.startswith("https://") and bool(host) and not _is_loopback(host)


class DatabaseSettings(BaseSettings):
    """What migrations need, and nothing more: `alembic upgrade` must not need API secrets."""

    model_config = SettingsConfigDict(env_prefix="CORE_", env_file=".env", extra="ignore")

    # postgresql+psycopg://user:password@host:5432/core. Secret because it holds the password;
    # no default, so a missing database is a startup error rather than a surprise later.
    database_url: SecretStr


class Settings(DatabaseSettings):
    # The S3_* fields are read by their alias; tests and code may still pass them by name.
    model_config = SettingsConfigDict(populate_by_name=True)

    # No default (R04): a forgotten CORE_ENVIRONMENT is a startup error, never production
    # running with local's rules. Compose sets it to local; deploys set it themselves (T0.13).
    environment: Environment
    log_level: str = "INFO"

    # redis://[:password@]host:6379/0. Rate limits (T1.6); a secret if it holds a password.
    redis_url: SecretStr
    # Token web sends in X-Service-Token. Only a request carrying it may say which IP the user
    # has (security.client_ip). Unset: core-api never trusts a client IP header.
    web_token: SecretStr | None = Field(default=None, min_length=32)

    # Email (T1.5). Locally Mailpit: no TLS, no login, web UI on http://localhost:8025.
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    email_from: str = "no-reply@localhost"
    # Where links in emails point: the web app, the only service on the internet (ARCH §3).
    # Outside local and test it must be set, and https: the links carry one-time tokens.
    # Empty = not set (see the validator below).
    web_base_url: str = Field(default="", validate_default=True)

    # Key for the keyed hash of IPs in the security log (T1.8): a plain hash of an IPv4 address
    # can be reversed by hashing all 2^32 of them. Outside local and test it must be set; locally
    # each process picks a random one.
    log_hash_key: SecretStr | None = Field(default=None, min_length=32, validate_default=True)

    ai_service_url: str = "http://127.0.0.1:8001"
    # Sent to ai-service in X-Service-Token. No default: core-api refuses to start without one,
    # the same rule ai-service applies on its side.
    ai_service_token: SecretStr = Field(min_length=32)
    # Below web's 3 s timeout for core-api, so a hung ai-service is reported as such
    # instead of web timing out and blaming core-api.
    ai_service_timeout_seconds: float = Field(default=2.0, gt=0)

    # Object storage (T4.5, ADR-0012): RustFS locally, R2 in production. Read from the S3_*
    # variables the stack already shares (.env.example, Compose's storage-init).
    # `s3_endpoint` is what core-api calls; `s3_public_endpoint` is what the browser reaches and
    # what upload URLs are signed for (SigV4 signs the host). Unset: the same as `s3_endpoint`.
    s3_endpoint: str = Field(
        default="http://127.0.0.1:9000", validation_alias="S3_ENDPOINT", validate_default=True
    )
    s3_public_endpoint: str | None = Field(
        default=None, validation_alias="S3_PUBLIC_ENDPOINT", validate_default=True
    )
    s3_bucket: str = Field(
        default="essity-files", validation_alias="S3_BUCKET", validate_default=True
    )
    # No default, in any environment: like the AI token, a missing key is a startup error.
    s3_access_key: SecretStr = Field(validation_alias="S3_ACCESS_KEY", min_length=1)
    s3_secret_key: SecretStr = Field(validation_alias="S3_SECRET_KEY", min_length=1)
    s3_region: str = Field(default="us-east-1", validation_alias="S3_REGION")  # R2: "auto"
    # How long an upload URL lives: "a few minutes" (PLAN T4.5). It is a write credential.
    s3_presign_seconds: int = Field(default=300, ge=60, le=900)
    # Per storage call, connect and read each. Confirm makes two calls while it holds its row.
    s3_timeout_seconds: float = Field(default=1.0, gt=0)

    # Upload limits (T4.5; anti-abuse with open sign-up). Byte totals count files being uploaded
    # as well as stored ones. The global cap keeps the store under R2's free 10 GB.
    document_max_bytes: int = Field(default=100 * MIB, gt=0)
    document_quota_bytes: int = Field(default=1 * GIB, gt=0)  # user, 26/10
    storage_global_quota_bytes: int = Field(default=8 * GIB, gt=0)
    document_uploads_per_hour: int = Field(default=30, ge=1)
    # An upload never confirmed, or refused, is deleted this long after its URL was signed.
    document_cleanup_after_seconds: int = Field(default=3600, gt=0)

    # A field validator, not a model one: a model validator's error prints the whole input,
    # secrets included, to the startup traceback; this one prints only the URL.
    @field_validator("web_token")
    @classmethod
    def _web_token_fits_environment(
        cls, token: SecretStr | None, info: ValidationInfo
    ) -> SecretStr | None:
        # Without it no client IP is trusted, so every user shares web's IP and its rate limits.
        if token is None and not _is_dev(info):
            raise ValueError("web_token must be set outside local and test")
        return token

    @field_validator("web_token", mode="before")
    @classmethod
    def _empty_web_token_is_unset(cls, token: object) -> object:
        return None if token == "" else token  # Compose passes an unset variable as ""

    @field_validator("smtp_host")
    @classmethod
    def _smtp_host_fits_environment(cls, host: str, info: ValidationInfo) -> str:
        # Empty too: Compose passes an unset variable as "" (Tester 12872a1).
        if not _is_dev(info) and (not host.strip() or _is_loopback(host)):
            raise ValueError("smtp_host must be a real mail server outside local and test")
        return host

    # Outside local and test, always: verification and reset emails carry one-time links, and a
    # login would otherwise go in clear (review 8489155; Mailpit from .env.example has no TLS).
    @field_validator("smtp_starttls")
    @classmethod
    def _starttls_fits_environment(cls, starttls: bool, info: ValidationInfo) -> bool:
        if not _is_dev(info) and not starttls:
            raise ValueError("smtp_starttls must be on outside local and test")
        return starttls

    @field_validator("email_from")
    @classmethod
    def _email_from_fits_environment(cls, address: str, info: ValidationInfo) -> str:
        local, at, domain = parseaddr(address)[1].rpartition("@")  # "Essity <a@b>" and "a@b"
        if not _is_dev(info) and (not (local and at and domain) or _is_loopback(domain)):
            raise ValueError(
                "email_from must be an address on a real domain outside local and test"
            )
        return address

    @field_validator("web_base_url")
    @classmethod
    def _web_url_fits_environment(cls, url: str, info: ValidationInfo) -> str:
        if _is_dev(info):
            return url or LOCAL_WEB_BASE_URL
        if not url.startswith("https://") or _is_loopback(urlsplit(url).hostname or ""):
            raise ValueError("web_base_url must be set to an https:// URL outside local and test")
        return url

    @field_validator("log_hash_key", mode="before")
    @classmethod
    def _empty_log_hash_key_is_unset(cls, key: object) -> object:
        return None if key == "" else key  # Compose passes an unset variable as ""

    @field_validator("log_hash_key")
    @classmethod
    def _log_hash_key_fits_environment(
        cls, key: SecretStr | None, info: ValidationInfo
    ) -> SecretStr | None:
        if key is None and not _is_dev(info):
            raise ValueError("log_hash_key must be set outside local and test")
        return key

    @field_validator("ai_service_url")
    @classmethod
    def _ai_url_fits_environment(cls, url: str, info: ValidationInfo) -> str:
        host = urlsplit(url).hostname or ""
        if not _is_dev(info) and (not host or _is_loopback(host)):
            raise ValueError("ai_service_url must be ai-service's address outside local and test")
        return url

    @field_validator("s3_endpoint")
    @classmethod
    def _s3_endpoint_fits_environment(cls, url: str, info: ValidationInfo) -> str:
        # boto3 takes "" as unset and would call Amazon S3 instead.
        if not urlsplit(url.strip()).hostname:
            raise ValueError("s3_endpoint must be a URL")
        if not _is_dev(info) and not _is_remote_https(url):
            raise ValueError("s3_endpoint must be an https:// URL outside local and test")
        return url

    @field_validator("s3_public_endpoint", mode="before")
    @classmethod
    def _empty_public_endpoint_is_unset(cls, url: object) -> object:
        return None if url == "" else url  # Compose passes an unset variable as ""

    @field_validator("s3_public_endpoint")
    @classmethod
    def _s3_public_endpoint_fits_environment(cls, url: str | None, info: ValidationInfo) -> str:
        # Upload URLs carry a write grant: over http anyone on the path could reuse one.
        if url is not None and not _is_dev(info) and not _is_remote_https(url):
            raise ValueError("s3_public_endpoint must be an https:// URL outside local and test")
        if url is None:
            # s3_endpoint is absent from info.data when it failed: the error is already raised.
            return info.data.get("s3_endpoint", "")
        return url

    @field_validator("s3_bucket")
    @classmethod
    def _s3_bucket_named(cls, bucket: str, info: ValidationInfo) -> str:
        if not _is_dev(info) and not bucket.strip():
            raise ValueError("s3_bucket must be set outside local and test")
        return bucket

    @field_validator("document_cleanup_after_seconds")
    @classmethod
    def _cleanup_after_urls_expire(cls, seconds: int, info: ValidationInfo) -> int:
        # A row deleted while its URL still works would let a PUT store a file nothing counts.
        presign = info.data.get("s3_presign_seconds")
        if presign is not None and seconds < 2 * presign:
            raise ValueError(
                "document_cleanup_after_seconds must be at least twice s3_presign_seconds"
            )
        return seconds


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # fields come from the environment
