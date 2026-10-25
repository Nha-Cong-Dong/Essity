"""Storage calls leave no file key, signature or credential in the logs (T4.5, ADR-0013).

boto3, botocore and urllib3 log signed requests and object paths at DEBUG; they are held at
WARNING like httpx, even when core-api runs at DEBUG.
"""

import hashlib
from collections.abc import Callable

import httpx2

from core_api.clients.storage import S3Storage
from object_store import S3_ACCESS_KEY


def test_storage_calls_log_nothing_secret_at_debug(
    log_output: Callable[[], str], s3_storage: S3Storage, object_key: str
) -> None:
    body = b"%PDF-1.7 logged?"
    digest = hashlib.sha256(body).hexdigest()
    upload = s3_storage.presign_put(
        object_key, size=len(body), sha256=digest, content_type="application/pdf", expires_in=60
    )
    httpx2.put(upload.url, content=body, headers=upload.headers)
    s3_storage.head(object_key)
    s3_storage.read_start(object_key, 5)
    s3_storage.delete(object_key)

    logged = log_output()
    assert object_key not in logged
    assert object_key.split("/")[1] not in logged  # the user id in the key
    assert "X-Amz-Signature" not in logged
    assert "Authorization" not in logged
    assert S3_ACCESS_KEY not in logged
    assert digest not in logged
