"""Rules for an uploaded document (T4.5, ADR-0012): what a file must be, and where it goes.

PDF, DOCX and PPTX (PRD AC4, T9.11; notebook photos are US-02's `note_file`). A file is checked
twice: by its name when the upload is requested, by its first bytes once it is stored. The name is
only what the user calls it: the object key is built from ids and the SHA-256, never from it.
"""

import re
import unicodedata
import uuid

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK"  # DOCX and PPTX are zips; ai-service checks which parts they hold
FORMATS = ("pdf", "docx", "pptx")
SHORT_NAME_MAX = 200  # document.short_name is String(200)

_SHA256 = re.compile(r"[0-9a-f]{64}")
# Control (Cc), format (Cf: zero-width, bidi overrides and isolates, BOM) and line/paragraph
# separators: invisible, or able to make a name read as something else on screen.
_DROPPED = frozenset({"Cc", "Cf", "Zl", "Zp"})


class UnsupportedFileTypeError(ValueError):
    """The file is not named as a PDF, DOCX or PPTX."""


class InvalidFilenameError(ValueError):
    """Nothing visible is left of the name once cleaned."""


def raw_key(user_id: uuid.UUID, subject_id: uuid.UUID, sha256: str) -> str:
    """Where the original file lives: `users/{user}/subjects/{subject}/raw/{sha256}.pdf`."""
    if not _SHA256.fullmatch(sha256):
        raise ValueError("sha256 must be 64 lowercase hex characters")
    return f"users/{user_id}/subjects/{subject_id}/raw/{sha256}.pdf"


def looks_like_pdf(start: bytes) -> bool:
    """Whether the file's first bytes are a PDF header. At offset 0 only (plan P20): the PDF
    spec tolerates junk in the first 1024 bytes, but nothing we expect needs it."""
    return start.startswith(PDF_MAGIC)


def looks_like_office(start: bytes) -> bool:
    """Whether the file's first bytes are a zip header (a DOCX or PPTX), at offset 0 only."""
    return start.startswith(ZIP_MAGIC)


def file_format(filename: str) -> str:
    """`pdf`, `docx` or `pptx`, by the extension of the name. Raise UnsupportedFileTypeError."""
    lowered = unicodedata.normalize("NFC", filename).strip().lower()
    for fmt in FORMATS:
        if lowered.endswith("." + fmt):
            return fmt
    raise UnsupportedFileTypeError  # no name in it: it must never reach a log


def short_name(filename: str) -> str:
    """The name shown for the document: the file name without its extension, composed (NFC), with no
    invisible or direction-changing characters, cut to SHORT_NAME_MAX.

    Raise UnsupportedFileTypeError when the name does not end in `.pdf`, `.docx` or `.pptx`,
    InvalidFilenameError when nothing visible is left.
    """
    name = unicodedata.normalize("NFC", filename).strip()
    extension = len(file_format(name)) + 1
    name = "".join(c for c in name[:-extension] if unicodedata.category(c) not in _DROPPED)
    name = name.strip()[:SHORT_NAME_MAX].strip()
    if not name:
        raise InvalidFilenameError
    return name
