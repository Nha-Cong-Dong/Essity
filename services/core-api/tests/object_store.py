"""The real S3-compatible store for tests (RustFS locally and in CI; T4.5).

Each test run works in a bucket of its own (`s3_bucket` in conftest.py), emptied and deleted at
the end, so runs never see each other's objects and nothing is left behind.
"""

import os
import uuid

import boto3
from botocore.config import Config
from mypy_boto3_s3 import S3Client

from core_api.clients.storage import S3Storage

S3_ENDPOINT = os.environ.get("CORE_TEST_S3_ENDPOINT", "http://127.0.0.1:9000")
S3_ACCESS_KEY = os.environ.get("CORE_TEST_S3_ACCESS_KEY", "change-me-local")
S3_SECRET_KEY = os.environ.get("CORE_TEST_S3_SECRET_KEY", "change-me-local-too")
S3_REGION = "us-east-1"


def admin_client() -> S3Client:
    return boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def create_bucket() -> str:
    bucket = f"test-{uuid.uuid4().hex[:12]}"
    admin_client().create_bucket(Bucket=bucket)
    return bucket


def drop_bucket(bucket: str) -> None:
    client = admin_client()
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for item in page.get("Contents", []):
            if "Key" in item:
                client.delete_object(Bucket=bucket, Key=item["Key"])
    client.delete_bucket(Bucket=bucket)


def storage_on(bucket: str, **overrides: object) -> S3Storage:
    values: dict[str, object] = {
        "endpoint": S3_ENDPOINT,
        "public_endpoint": S3_ENDPOINT,
        "bucket": bucket,
        "access_key": S3_ACCESS_KEY,
        "secret_key": S3_SECRET_KEY,
        "region": S3_REGION,
        "timeout_seconds": 5,
    }
    values.update(overrides)
    return S3Storage.connect(**values)  # pyright: ignore[reportArgumentType]
