"""Edges of `S3Storage` the happy path does not show (review of 89d6529, C1–C3, C6)."""

import uuid
from typing import Any, cast

import pytest
from mypy_boto3_s3 import S3Client

from core_api.clients.storage import S3Storage, StorageUnavailableError, StoredObject
from object_store import storage_on


def test_a_missing_bucket_is_an_error_not_a_missing_object(object_key: str) -> None:
    # A mistyped S3_BUCKET must fail closed: delete would otherwise "succeed", and the
    # cleanup job delete rows whose files it never reached.
    storage = storage_on(f"test-missing-{uuid.uuid4().hex[:12]}")

    with pytest.raises(StorageUnavailableError):
        storage.delete(object_key)
    with pytest.raises(StorageUnavailableError):
        storage.read_start(object_key, 5)
    # HEAD has no body, so its 404 cannot say which is missing (tester L1): confirm must answer
    # 503, not "upload incomplete" for ever.
    with pytest.raises(StorageUnavailableError):
        storage.head(object_key)


def test_read_start_of_a_missing_object_is_an_error(s3_storage: S3Storage, object_key: str):
    with pytest.raises(StorageUnavailableError):
        s3_storage.read_start(object_key, 5)


def test_one_attempt_per_call(s3_storage: S3Storage) -> None:
    # botocore's defaults retry 4 more times, each with a 60 s timeout.
    for client in (s3_storage._internal, s3_storage._public):  # pyright: ignore[reportPrivateUsage]
        retries = cast(dict[str, Any], client.meta.config.retries)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        assert retries["total_max_attempts"] == 1


class _Body:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.closed = False

    def read(self, length: int) -> bytes:
        return self.data[:length]

    def close(self) -> None:
        self.closed = True


class _Stub:
    """Just the client calls `S3Storage` makes, answering what a store might."""

    def __init__(self, checksum: str | None = None, body: bytes = b"") -> None:
        self.checksum = checksum
        self.body = _Body(body)

    def head_object(self, **_: object) -> dict[str, object]:
        found: dict[str, object] = {"ContentLength": 5}
        if self.checksum is not None:
            found["ChecksumSHA256"] = self.checksum
        return found

    def get_object(self, **_: object) -> dict[str, object]:
        return {"Body": self.body}


def stub_storage(stub: _Stub) -> S3Storage:
    client = cast(S3Client, stub)
    return S3Storage(client, client, "bucket")


def test_a_stored_checksum_is_turned_into_hex() -> None:
    # base64 of SHA-256("abc"), written out rather than computed with the code's own helper.
    stub = _Stub(checksum="ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=")
    assert stub_storage(stub).head("key") == StoredObject(
        size=5, sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.parametrize("checksum", ["abc-1", "not base64!", "YWJj"])
def test_an_unreadable_checksum_never_matches(checksum: str) -> None:
    # A multipart checksum ("...-1"), junk, or base64 of something that is not 32 bytes: the
    # file cannot be shown to be the declared one, so confirm must refuse it.
    stored = stub_storage(_Stub(checksum=checksum)).head("key")
    assert stored == StoredObject(size=5, sha256="")


def test_no_stored_checksum_is_none() -> None:
    assert stub_storage(_Stub()).head("key") == StoredObject(size=5, sha256=None)


def test_read_start_closes_the_body() -> None:
    # A store ignoring Range sends the whole file: the connection must still go back.
    stub = _Stub(body=b"%PDF-1.7" + b"x" * 1000)
    assert stub_storage(stub).read_start("key", 5) == b"%PDF-"
    assert stub.body.closed
