"""`S3Storage` on the real store (T4.5, ADR-0012): what a presigned PUT lets a browser do.

These tests are the evidence for the plan's storage matrix: the URL is short-lived, signs the
size, the type, the SHA-256 and "only if absent", and the store enforces each of them. Run on
RustFS locally and in CI; the same file runs against an R2 test bucket when there is one (T0.13).
"""

import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from core_api.clients.storage import S3Storage, StorageUnavailableError, StoredObject
from object_store import storage_on

PDF = b"%PDF-1.7\n" + b"x" * 200 + b"\n%%EOF\n"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def put(storage: S3Storage, key: str, body: bytes, *, declared: bytes = PDF, expires: int = 60):
    upload = storage.presign_put(
        key,
        size=len(declared),
        sha256=sha256_hex(declared),
        content_type="application/pdf",
        expires_in=expires,
    )
    return upload, httpx2.put(upload.url, content=body, headers=upload.headers)


def test_presigned_put_of_the_declared_file_is_stored(s3_storage: S3Storage, object_key: str):
    _, response = put(s3_storage, object_key, PDF)

    assert response.status_code == 200, response.text
    stored = s3_storage.head(object_key)
    assert stored == StoredObject(size=len(PDF), sha256=sha256_hex(PDF))
    assert s3_storage.read_start(object_key, 5) == b"%PDF-"


def test_url_signs_size_type_checksum_and_only_if_absent(s3_storage: S3Storage, object_key: str):
    upload, _ = put(s3_storage, object_key, PDF)

    query = parse_qs(urlsplit(upload.url).query)
    signed = set(query["X-Amz-SignedHeaders"][0].split(";"))
    assert {
        "content-length",
        "content-type",
        "host",
        "if-none-match",
        "x-amz-checksum-sha256",
    } <= signed
    # The browser must send exactly these; Content-Length it sets itself from the body.
    assert upload.headers["Content-Type"] == "application/pdf"
    assert upload.headers["If-None-Match"] == "*"
    assert "x-amz-checksum-sha256" in upload.headers


def test_other_bytes_of_the_same_size_are_refused(s3_storage: S3Storage, object_key: str):
    other = PDF.replace(b"x", b"y")
    assert len(other) == len(PDF)

    _, response = put(s3_storage, object_key, other)

    assert response.status_code == 400  # BadDigest: the store checked the signed SHA-256
    assert s3_storage.head(object_key) is None


def test_a_bigger_body_is_refused(s3_storage: S3Storage, object_key: str):
    _, response = put(s3_storage, object_key, PDF + b"more")

    assert response.status_code == 403  # Content-Length is signed
    assert s3_storage.head(object_key) is None


def test_dropping_a_signed_header_is_refused(s3_storage: S3Storage, object_key: str):
    upload = s3_storage.presign_put(
        object_key,
        size=len(PDF),
        sha256=sha256_hex(PDF),
        content_type="application/pdf",
        expires_in=60,
    )
    headers = {k: v for k, v in upload.headers.items() if k != "If-None-Match"}

    response = httpx2.put(upload.url, content=PDF, headers=headers)

    assert response.status_code == 403
    assert s3_storage.head(object_key) is None


def test_a_stored_file_is_never_overwritten(s3_storage: S3Storage, object_key: str):
    # ADR-0012: raw files are immutable. The URL is still alive after the first PUT.
    upload, first = put(s3_storage, object_key, PDF)
    assert first.status_code == 200

    second = httpx2.put(upload.url, content=PDF, headers=upload.headers)

    assert second.status_code == 412
    assert s3_storage.head(object_key) == StoredObject(size=len(PDF), sha256=sha256_hex(PDF))


def test_an_expired_url_is_refused(s3_storage: S3Storage, object_key: str):
    upload = s3_storage.presign_put(
        object_key,
        size=len(PDF),
        sha256=sha256_hex(PDF),
        content_type="application/pdf",
        expires_in=1,
    )
    time.sleep(2.5)

    response = httpx2.put(upload.url, content=PDF, headers=upload.headers)

    assert response.status_code == 403
    assert s3_storage.head(object_key) is None


def test_the_url_points_at_the_public_endpoint(s3_bucket: str, object_key: str):
    # SigV4 signs the host: the browser's URL must name the address the browser can reach.
    storage = storage_on(s3_bucket, public_endpoint="https://files.essity.example")

    upload = storage.presign_put(
        object_key, size=1, sha256=sha256_hex(b"x"), content_type="application/pdf", expires_in=60
    )

    assert upload.url.startswith(f"https://files.essity.example/{s3_bucket}/{object_key}?")


def test_head_of_a_missing_object_is_none(s3_storage: S3Storage, object_key: str):
    assert s3_storage.head(object_key) is None


def test_delete_removes_and_is_harmless_twice(s3_storage: S3Storage, object_key: str):
    put(s3_storage, object_key, PDF)

    s3_storage.delete(object_key)
    s3_storage.delete(object_key)

    assert s3_storage.head(object_key) is None


def test_read_start_reads_only_the_first_bytes(s3_storage: S3Storage, object_key: str):
    put(s3_storage, object_key, PDF)

    assert s3_storage.read_start(object_key, 16) == PDF[:16]


def test_an_unreachable_store_raises_storage_unavailable(s3_bucket: str, object_key: str):
    # A non-routable address: the connection hangs, so only our timeout ends the call.
    storage = storage_on(s3_bucket, endpoint="http://10.255.255.1:9000", timeout_seconds=0.5)

    for call in (
        lambda: storage.head(object_key),
        lambda: storage.read_start(object_key, 5),
        lambda: storage.delete(object_key),
    ):
        started = time.monotonic()
        with pytest.raises(StorageUnavailableError):
            call()
        # One attempt, no retries: botocore's defaults (60 s, 5 tries) would hold a request
        # and its row lock for minutes.
        assert time.monotonic() - started < 1.5


def assert_hides_the_request(error: StorageUnavailableError, object_key: str) -> None:
    # botocore's messages carry the full URL: the error must not, nor chain to one that does,
    # since a logged traceback prints the chain.
    assert object_key not in str(error)
    assert error.__cause__ is None
    assert error.__suppress_context__


def test_storage_errors_hide_the_key(s3_bucket: str, object_key: str):
    storage = storage_on(s3_bucket, endpoint="http://127.0.0.1:9", timeout_seconds=1)

    with pytest.raises(StorageUnavailableError) as error:
        storage.head(object_key)

    assert_hides_the_request(error.value, object_key)


def test_wrong_credentials_raise_storage_unavailable(s3_bucket: str, object_key: str):
    storage = storage_on(s3_bucket, secret_key="not-the-secret")

    with pytest.raises(StorageUnavailableError) as error:
        storage.head(object_key)
    assert_hides_the_request(error.value, object_key)
    with pytest.raises(StorageUnavailableError):
        storage.read_start(object_key, 5)
    with pytest.raises(StorageUnavailableError):
        storage.delete(object_key)
