"""Rules for an uploaded document (T4.5, ADR-0012): what a file must be, and where it goes.

Only PDF for now (PRD AC4; notebook photos are US-02's `note_file`). A file is checked twice:
by its name when the upload is requested, by its first bytes once it is stored. The name is
only what the user calls it: the object key is built from ids and the SHA-256, never from it.
"""

import re
import unicodedata
import uuid

PDF_MAGIC = b"%PDF-"
SHORT_NAME_MAX = 200  # document.short_name is String(200)

_SHA256 = re.compile(r"[0-9a-f]{64}")
# Control (Cc), format (Cf: zero-width, bidi overrides and isolates, BOM) and line/paragraph
# separators: invisible, or able to make a name read as something else on screen.
_DROPPED = frozenset({"Cc", "Cf", "Zl", "Zp"})


class UnsupportedFileTypeError(ValueError):
    """The file is not named as a PDF."""


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


def short_name(filename: str) -> str:
    """The name shown for the document: the file name without `.pdf`, composed (NFC), with no
    invisible or direction-changing characters, cut to SHORT_NAME_MAX.

    Raise UnsupportedFileTypeError when the name does not end in `.pdf`, InvalidFilenameError
    when nothing visible is left.
    """
    name = unicodedata.normalize("NFC", filename).strip()
    if not name.lower().endswith(".pdf"):
        raise UnsupportedFileTypeError  # no name in it: it must never reach a log
    name = "".join(c for c in name[: -len(".pdf")] if unicodedata.category(c) not in _DROPPED)
    name = name.strip()[:SHORT_NAME_MAX].strip()
    if not name:
        raise InvalidFilenameError
    return name
