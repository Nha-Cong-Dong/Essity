"""A storage double for API tests of documents (T4.5).

It answers like the real store would, from objects the test puts in it. Checksums are given as
the store sends them (base64), written by the test, never computed with the code's helpers
(plan P12). End-to-end tests on RustFS cover the real thing.
"""

import base64
from dataclasses import dataclass, field

from core_api.clients.storage import PresignedPut, StorageUnavailableError, StoredObject


@dataclass
class Presigned:
    key: str
    size: int
    sha256: str
    content_type: str
    expires_in: int


@dataclass
class FakeStorage:
    objects: dict[str, tuple[bytes, str | None]] = field(  # key → body, base64 SHA-256
        default_factory=dict[str, tuple[bytes, str | None]]
    )
    presigned: list[Presigned] = field(default_factory=list[Presigned])
    deleted: list[str] = field(default_factory=list[str])
    down: bool = False

    def presign_put(
        self, key: str, *, size: int, sha256: str, content_type: str, expires_in: int
    ) -> PresignedPut:
        self.presigned.append(Presigned(key, size, sha256, content_type, expires_in))
        return PresignedPut(
            url=f"https://files.example/bucket/{key}?X-Amz-Expires={expires_in}&X-Amz-Signature=s",
            headers={
                "Content-Type": content_type,
                "x-amz-checksum-sha256": "c2lnbmVk",
                "If-None-Match": "*",
            },
        )

    def put(self, key: str, body: bytes, checksum_b64: str | None) -> None:
        self.objects[key] = (body, checksum_b64)

    def head(self, key: str) -> StoredObject | None:
        if self.down:
            raise StorageUnavailableError("storage unreachable (test)")
        if key not in self.objects:
            return None
        body, checksum = self.objects[key]
        return StoredObject(size=len(body), sha256=_hex(checksum))

    def read_start(self, key: str, length: int) -> bytes:
        if self.down or key not in self.objects:
            raise StorageUnavailableError("storage unreachable (test)")
        return self.objects[key][0][:length]

    def delete(self, key: str) -> None:
        if self.down:
            raise StorageUnavailableError("storage unreachable (test)")
        self.deleted.append(key)
        self.objects.pop(key, None)


def _hex(checksum_b64: str | None) -> str | None:
    return None if checksum_b64 is None else base64.b64decode(checksum_b64).hex()
