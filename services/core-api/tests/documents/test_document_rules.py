"""Rules for an uploaded document (T4.5, ADR-0012): what a file must be, and where it goes."""

import uuid

import pytest

from core_api.domain.documents import (
    InvalidFilenameError,
    UnsupportedFileTypeError,
    looks_like_pdf,
    raw_key,
    short_name,
)

SHA = "ab" * 32


def test_raw_key_is_user_subject_raw_sha_pdf() -> None:
    user, subject = uuid.uuid4(), uuid.uuid4()
    assert raw_key(user, subject, SHA) == f"users/{user}/subjects/{subject}/raw/{SHA}.pdf"


@pytest.mark.parametrize("sha", ["AB" * 32, "ab" * 31, "zz" * 32, "../" + "a" * 61, ""])
def test_raw_key_takes_only_a_lowercase_hex_sha256(sha: str) -> None:
    with pytest.raises(ValueError, match="sha256"):
        raw_key(uuid.uuid4(), uuid.uuid4(), sha)


@pytest.mark.parametrize(
    "start",
    [b"%PDF-1.7\n%\xe2\xe3", b"%PDF-2.0", b"%PDF-"],
)
def test_pdf_magic_at_the_start_is_a_pdf(start: bytes) -> None:
    assert looks_like_pdf(start)


@pytest.mark.parametrize(
    "start",
    [
        b"\x89PNG\r\n\x1a\n",  # a PNG named .pdf
        b"\xff\xd8\xff\xe0",  # a JPEG
        b"PK\x03\x04",  # a docx/zip
        b"junk%PDF-1.7",  # the magic not at offset 0 (plan P20: offset 0 only)
        b" %PDF-1.7",
        b"%PDF",  # cut short
        b"%pdf-1.7",
        b"",
    ],
)
def test_anything_else_is_not_a_pdf(start: bytes) -> None:
    assert not looks_like_pdf(start)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Mạng máy tính - Chương 3.pdf", "Mạng máy tính - Chương 3"),
        ("slides.PDF", "slides"),
        ("  bài giảng.pdf  ", "bài giảng"),
        ("a.b.c.pdf", "a.b.c"),
        # Combining marks (Unikey "Unicode tổ hợp") are composed, as for subject names.
        ("Chương.pdf", "Chương"),
    ],
)
def test_short_name_is_the_filename_without_pdf(filename: str, expected: str) -> None:
    assert short_name(filename) == expected


def test_short_name_drops_control_and_bidi_characters() -> None:
    # A right-to-left override would show "fdp.exe" as "exe.pdf" on screen.
    assert short_name("evil‮gnp.pdf") == "evilgnp"
    assert short_name("a⁦b⁩c‏d.pdf") == "abcd"
    assert short_name("tab\there\x00.pdf") == "tabhere"


def test_short_name_is_cut_to_200_characters() -> None:
    assert short_name("ư" * 250 + ".pdf") == "ư" * 200


@pytest.mark.parametrize("filename", [".pdf", "   .pdf", "‮.pdf", "​​.pdf"])
def test_a_name_that_is_nothing_once_cleaned_is_refused(filename: str) -> None:
    with pytest.raises(InvalidFilenameError):
        short_name(filename)


@pytest.mark.parametrize(
    "filename",
    [
        "scan.png",  # PLAN T4.5: a PDF renamed .png is refused
        "notes.pdf.png",
        "slides.pptx",
        "pdf",
        "slides.pdf.",
    ],
)
def test_only_pdf_names_are_accepted(filename: str) -> None:
    with pytest.raises(UnsupportedFileTypeError):
        short_name(filename)
