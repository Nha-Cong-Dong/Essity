"""Object storage for users' files (T4.5, ADR-0012): R2 in production, RustFS locally.

core-api never carries a file. It signs a short-lived PUT for the browser, then looks at what
arrived: its size and stored SHA-256 (`head`) and its first bytes (`read_start`).

A presigned PUT signs, besides the host:
- `Content-Length`: the store refuses a body of any other size;
- `Content-Type`;
- `x-amz-checksum-sha256`: a store that checks it refuses other bytes (RustFS does);
- `If-None-Match: *`: the PUT only creates, so a stored file is never overwritten (412), even
  on a store that ignores the checksum.

Two endpoints: the internal one core-api calls, and the public one the browser reaches. SigV4
signs the host, so the URL must be signed for the address the browser will use. Presigning
makes no network call.

A presigned URL is a credential until it expires: never log it.
"""

from __future__ import annotations

import base64
import binascii
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from core_api.config import Settings

if TYPE_CHECKING:  # boto3-stubs is a dev-only group: never import it at runtime
    from mypy_boto3_s3 import S3Client


class StorageUnavailableError(Exception):
    """The store did not answer, refused our credentials, or answered with an error."""


@dataclass(frozen=True)
class PresignedPut:
    url: str
    headers: dict[str, str]  # to send as they are; the browser adds Content-Length itself


@dataclass(frozen=True)
class StoredObject:
    size: int
    # Hex. None when the store keeps no SHA-256 for the object; "" when what it keeps is not one.
    sha256: str | None


class ObjectStorage(Protocol):
    def presign_put(
        self, key: str, *, size: int, sha256: str, content_type: str, expires_in: int
    ) -> PresignedPut: ...

    def head(self, key: str) -> StoredObject | None: ...

    def read_start(self, key: str, length: int) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def write(self, key: str, data: bytes, *, content_type: str) -> None:
        """Store a small file core-api itself makes (a grading request, T4.19)."""
        ...

    def read(self, key: str, *, max_bytes: int) -> bytes | None:
        """A small file ai-service wrote (a grading result), or None when it is not there.
        StorageUnavailableError when it is longer than `max_bytes`, as when the store fails."""
        ...


def _client(
    endpoint: str, access_key: str, secret_key: str, region: str, timeout_seconds: float
) -> S3Client:
    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        # boto3 >= 1.36 adds CRC32 checksums by default, which some S3-compatible stores refuse.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        connect_timeout=timeout_seconds,
        read_timeout=timeout_seconds,
        retries={"total_max_attempts": 1, "mode": "standard"},  # no retry: one call, one timeout
    )
    return boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=config,
    )


def _reason(error: Exception) -> str:
    """What went wrong, without the request: botocore's messages carry the URL and key."""
    if isinstance(error, ClientError):
        return f"storage answered {error.response.get('Error', {}).get('Code', 'an error')}"
    return f"storage unreachable ({type(error).__name__})"


def _sha256_hex(checksum: str) -> str:
    """The stored base64 SHA-256 as hex; "" (which matches no SHA-256) when it is not one: a
    multipart checksum ("...-2") or junk cannot show the file is the declared one."""
    try:
        digest = base64.b64decode(checksum, validate=True)
    except binascii.Error:
        return ""
    return digest.hex() if len(digest) == 32 else ""


def _not_found(error: ClientError) -> bool:
    code = error.response.get("Error", {}).get("Code", "")
    status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in {"404", "NoSuchKey", "NotFound"} or status == 404


class S3Storage:
    def __init__(self, internal: S3Client, public: S3Client, bucket: str) -> None:
        self._internal = internal
        self._public = public
        self._bucket = bucket

    @classmethod
    def connect(
        cls,
        *,
        endpoint: str,
        public_endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
        timeout_seconds: float,
    ) -> S3Storage:
        def client(url: str) -> S3Client:
            return _client(url, access_key, secret_key, region, timeout_seconds)

        return cls(client(endpoint), client(public_endpoint), bucket)

    @classmethod
    def from_settings(cls, settings: Settings) -> S3Storage:
        return cls.connect(
            endpoint=settings.s3_endpoint,
            public_endpoint=settings.s3_public_endpoint or settings.s3_endpoint,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key.get_secret_value(),
            secret_key=settings.s3_secret_key.get_secret_value(),
            region=settings.s3_region,
            timeout_seconds=settings.s3_timeout_seconds,
        )

    def presign_put(
        self, key: str, *, size: int, sha256: str, content_type: str, expires_in: int
    ) -> PresignedPut:
        checksum = base64.b64encode(bytes.fromhex(sha256)).decode()
        url = self._public.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentLength": size,
                "ContentType": content_type,
                "ChecksumSHA256": checksum,
                "IfNoneMatch": "*",
            },
            ExpiresIn=expires_in,
        )
        headers = {
            "Content-Type": content_type,
            "x-amz-checksum-sha256": checksum,
            "If-None-Match": "*",
        }
        return PresignedPut(url=url, headers=headers)

    def head(self, key: str) -> StoredObject | None:
        try:
            found = self._internal.head_object(Bucket=self._bucket, Key=key, ChecksumMode="ENABLED")
        except ClientError as error:
            if _not_found(error) and self._bucket_exists():
                return None
            raise StorageUnavailableError(_reason(error)) from None
        except BotoCoreError as error:
            raise StorageUnavailableError(_reason(error)) from None
        checksum = found.get("ChecksumSHA256", "")
        return StoredObject(
            size=found["ContentLength"],
            sha256=_sha256_hex(checksum) if checksum else None,
        )

    def _bucket_exists(self) -> bool:
        """Whether the bucket is there. A HEAD has no body, so its 404 cannot say whether the
        object or the bucket is missing; a mistyped bucket must fail closed (tester L1). Asked
        only after a 404, which confirm rarely meets."""
        try:
            self._internal.head_bucket(Bucket=self._bucket)
        except ClientError as error:
            if _not_found(error):
                return False
            raise StorageUnavailableError(_reason(error)) from None
        except BotoCoreError as error:
            raise StorageUnavailableError(_reason(error)) from None
        return True

    def read_start(self, key: str, length: int) -> bytes:
        """The first `length` bytes of the object (fewer if it is shorter)."""
        try:
            found = self._internal.get_object(
                Bucket=self._bucket, Key=key, Range=f"bytes=0-{length - 1}"
            )
            with closing(found["Body"]) as body:  # a store ignoring Range sends it all
                return body.read(length)
        except (ClientError, BotoCoreError) as error:
            raise StorageUnavailableError(_reason(error)) from None

    def delete(self, key: str) -> None:
        """Delete the object. A key that is not there is not an error (S3 answers 204); a
        bucket that is not there is, so a mistyped bucket fails closed."""
        try:
            self._internal.delete_object(Bucket=self._bucket, Key=key)
        except (ClientError, BotoCoreError) as error:
            raise StorageUnavailableError(_reason(error)) from None

    def write(self, key: str, data: bytes, *, content_type: str) -> None:
        try:
            self._internal.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except (ClientError, BotoCoreError) as error:
            raise StorageUnavailableError(_reason(error)) from None

    def read(self, key: str, *, max_bytes: int) -> bytes | None:
        try:
            found = self._internal.get_object(Bucket=self._bucket, Key=key)
            with closing(found["Body"]) as body:
                if int(found.get("ContentLength", 0)) > max_bytes:
                    raise StorageUnavailableError("storage object too large")
                return body.read()
        except ClientError as error:
            if _not_found(error) and self._bucket_exists():
                return None
            raise StorageUnavailableError(_reason(error)) from None
        except BotoCoreError as error:
            raise StorageUnavailableError(_reason(error)) from None
