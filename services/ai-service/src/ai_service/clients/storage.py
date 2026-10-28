"""The object storage ai-service reads documents from and writes derived files to (T4.7).

A thin port over S3 (MinIO/RustFS locally, R2 in production), so handlers are tested against an
in-memory fake. Errors carry no text of their own: a message from boto holds the endpoint and
the object key, which the log must not see (keys name a user and a subject).
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false

from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class StorageUnavailable(Exception):
    """The storage did not answer, or answered with a server error: try again later."""


class ObjectNotFound(Exception):
    """No object under that key (deterministic: asking again finds nothing)."""


class ObjectTooLarge(Exception):
    """The object is larger than the caller allowed."""


class ObjectStorage(Protocol):
    def get(self, key: str, *, max_bytes: int) -> bytes:
        """The object's bytes. Raises ObjectNotFound, ObjectTooLarge (checked before it is
        read) or StorageUnavailable."""
        ...

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        """Write (overwrite) one object. Raises StorageUnavailable."""
        ...


_NOT_FOUND = frozenset({"404", "NoSuchKey", "NotFound"})


class S3Storage:
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        timeout_s: float = 10.0,
    ) -> None:
        self._bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=timeout_s,
                read_timeout=timeout_s,
                retries={"max_attempts": 1},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def get(self, key: str, *, max_bytes: int) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in _NOT_FOUND:
                raise ObjectNotFound from None
            raise StorageUnavailable from None
        except BotoCoreError:
            raise StorageUnavailable from None
        body = response["Body"]
        try:
            if int(response.get("ContentLength", 0)) > max_bytes:
                raise ObjectTooLarge
            return bytes(body.read())
        except (ClientError, BotoCoreError, OSError):
            raise StorageUnavailable from None
        finally:
            body.close()

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except (ClientError, BotoCoreError):
            raise StorageUnavailable from None
