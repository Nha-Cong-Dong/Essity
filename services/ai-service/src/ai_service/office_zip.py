"""Checks on an OOXML file (DOCX, PPTX) before any library parses it (T7.3, ADR-0011).

An OOXML file is a zip. A zip bomb is caught here, from the central directory, before a byte is
inflated: too many entries, too large when inflated, or an entry compressed far beyond what real
documents reach. A macro-enabled file (it carries `vbaProject.bin`) is refused: nothing in
ai-service executes macros, and refusing is simpler than promising the library never will.
"""

import io
import zipfile
from dataclasses import dataclass

OfficeErrorCode = str


class OfficeError(Exception):
    """The file cannot be read as asked. `code` is stable and safe to store or log, and is the
    whole message: the library's text stays on `__cause__`."""

    def __init__(self, code: OfficeErrorCode) -> None:
        super().__init__(code)
        self.code = code

    def __reduce__(self) -> tuple[type["OfficeError"], tuple[OfficeErrorCode]]:
        return (OfficeError, (self.code,))


@dataclass(frozen=True)
class ZipLimits:
    max_bytes: int = 50 * 1024 * 1024
    max_uncompressed_bytes: int = 250 * 1024 * 1024
    max_entries: int = 5000
    # Real documents rarely pass 20:1 over a whole file; 100:1 on one entry is a bomb.
    max_entry_ratio: int = 100
    # Ratios only mean something above this size (a tiny XML part compresses 100:1 honestly).
    ratio_floor_bytes: int = 1024 * 1024


def check_zip(data: bytes, limits: ZipLimits, required: str) -> None:
    """Raise OfficeError("too_large" | "malformed" | "zip_bomb" | "macros"). `required` is the
    part that makes the zip the right kind of document ("word/document.xml")."""
    if len(data) > limits.max_bytes:
        raise OfficeError("too_large")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError) as error:
        raise OfficeError("malformed") from error
    if len(infos) > limits.max_entries:
        raise OfficeError("zip_bomb")
    names = {info.filename.lower() for info in infos}
    if required.lower() not in names:
        raise OfficeError("malformed")
    total = 0
    for info in infos:
        total += info.file_size
        if total > limits.max_uncompressed_bytes:
            raise OfficeError("zip_bomb")
        if (
            info.file_size > limits.ratio_floor_bytes
            and info.file_size > limits.max_entry_ratio * max(info.compress_size, 1)
        ):
            raise OfficeError("zip_bomb")
    if any(name.endswith("vbaproject.bin") for name in names):
        raise OfficeError("macros")
