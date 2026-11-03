"""`S3Storage.delete_prefix` against a client double (T6.3 tester round 2): what a real store
rarely shows on demand, a partial refusal and the size of each DeleteObjects call."""

from typing import Any, cast

import pytest
from mypy_boto3_s3 import S3Client

from core_api.clients.storage import S3Storage, StorageUnavailableError


class _Pages:
    def __init__(self, pages: list[list[str]]) -> None:
        self.pages = pages

    def paginate(self, **_: object) -> list[dict[str, Any]]:
        return [{"Contents": [{"Key": key} for key in page]} for page in self.pages]


class _Client:
    """`list_objects_v2` pages and `delete_objects`, refusing from call `refuse_from` on."""

    def __init__(self, pages: list[list[str]], refuse_from: int | None = None) -> None:
        self.pages = pages
        self.refuse_from = refuse_from
        self.calls: list[list[str]] = []

    def get_paginator(self, name: str) -> _Pages:
        assert name == "list_objects_v2"
        return _Pages(self.pages)

    def delete_objects(self, **kwargs: Any) -> dict[str, Any]:
        keys = [item["Key"] for item in kwargs["Delete"]["Objects"]]
        self.calls.append(keys)
        if self.refuse_from is not None and len(self.calls) >= self.refuse_from:
            return {"Errors": [{"Key": keys[0], "Code": "AccessDenied"}]}
        return {}


def _storage(client: _Client) -> S3Storage:
    stub = cast(S3Client, client)
    return S3Storage(stub, stub, "bucket")


def _keys(count: int, start: int = 0) -> list[str]:
    return [f"users/u/derived/{index}.json" for index in range(start, start + count)]


def test_t63_a_partial_refusal_is_an_error_not_a_success() -> None:
    # Red when: the `Errors` of a DeleteObjects answer are ignored, so objects the store refused
    # stay while erase-user reports them deleted (and the sweep has nothing left to retry).
    client = _Client([_keys(60)], refuse_from=2)
    with pytest.raises(StorageUnavailableError):
        _storage(client).delete_prefix("users/u/")


def test_t63_objects_go_in_small_batches_each_once_and_are_counted() -> None:
    # Red when: one DeleteObjects call carries a whole 1000-key page again (12 s on the local
    # store, past the 1 s read timeout: a big user can never be erased), a key is skipped or
    # sent twice, or the count is not the number of objects deleted.
    first, second = _keys(1000), _keys(7, start=1000)
    client = _Client([first, second, []])

    assert _storage(client).delete_prefix("users/u/") == 1007
    assert max(len(call) for call in client.calls) <= 100
    sent = [key for call in client.calls for key in call]
    assert sorted(sent) == sorted(first + second)
