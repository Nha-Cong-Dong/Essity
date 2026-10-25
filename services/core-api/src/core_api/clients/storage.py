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

import base64
from dataclasses import dataclass
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from mypy_boto3_s3 import S3Client

from core_api.config import Settings


class StorageUnavailableError(Exception):
    """The store did not answer, refused our credentials, or answered with an error."""


@dataclass(frozen=True)
class PresignedPut:
    url: str
    headers: dict[str, str]  # to send as they are; the browser adds Content-Length itself


@dataclass(frozen=True)
class StoredObject:
    size: int
    sha256: str | None  # hex; None when the store does not keep a SHA-256 for the object


class ObjectStorage(Protocol):
    def presign_put(
        self, key: str, *, size: int, sha256: str, content_type: str, expires_in: int
    ) -> PresignedPut: ...

    def head(self, key: str) -> StoredObject | None: ...

    def read_start(self, key: str, length: int) -> bytes: ...

    def delete(self, key: str) -> None: ...


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
    ) -> "S3Storage":
        def client(url: str) -> S3Client:
            return _client(url, access_key, secret_key, region, timeout_seconds)

        return cls(client(endpoint), client(public_endpoint), bucket)

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3Storage":
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
            if _not_found(error):
                return None
            raise StorageUnavailableError(_reason(error)) from None
        except BotoCoreError as error:
            raise StorageUnavailableError(_reason(error)) from None
        checksum = found.get("ChecksumSHA256")
        return StoredObject(
            size=found["ContentLength"],
            sha256=base64.b64decode(checksum).hex() if checksum else None,
        )

    def read_start(self, key: str, length: int) -> bytes:
        """The first `length` bytes of the object (fewer if it is shorter)."""
        try:
            found = self._internal.get_object(
                Bucket=self._bucket, Key=key, Range=f"bytes=0-{length - 1}"
            )
            return found["Body"].read(length)
        except (ClientError, BotoCoreError) as error:
            raise StorageUnavailableError(_reason(error)) from None

    def delete(self, key: str) -> None:
        """Delete the object; deleting one that is not there is not an error."""
        try:
            self._internal.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if not _not_found(error):
                raise StorageUnavailableError(_reason(error)) from None
        except BotoCoreError as error:
            raise StorageUnavailableError(_reason(error)) from None
