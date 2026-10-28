"""The child process the PDF is read in (T4.7, ADR-0011): a crash or a loop in PDFium ends
that process only, and every file gets a fresh one."""

import os
import time

import pytest

from ai_service.pdf import PdfError, PdfLimits
from ai_service.tasks.index_document import Analysis, analyze, run_isolated
from tests.pdf.helpers import Page, make_pdf

LIMITS = PdfLimits()


def crash(data: bytes, limits: PdfLimits) -> Analysis:
    os._exit(139)  # what a segfault looks like from outside


def loop(data: bytes, limits: PdfLimits) -> Analysis:
    time.sleep(60)
    raise AssertionError("not reached")


def refuse(data: bytes, limits: PdfLimits) -> Analysis:
    raise PdfError("encrypted")


def test_t47_reads_a_pdf_in_a_child() -> None:
    result = run_isolated(
        make_pdf([Page(text="one two three four five six")]), LIMITS, timeout_s=60
    )
    assert result.page_count == 1
    assert result == analyze(make_pdf([Page(text="one two three four five six")]), LIMITS)


def test_t47_crash_in_the_child_is_malformed() -> None:
    with pytest.raises(PdfError) as error:
        run_isolated(b"x", LIMITS, timeout_s=60, target=crash)
    assert error.value.code == "malformed"


def test_t47_loop_in_the_child_is_killed_at_the_deadline() -> None:
    started = time.monotonic()
    with pytest.raises(PdfError) as error:
        run_isolated(b"x", LIMITS, timeout_s=1, target=loop)
    assert error.value.code == "deadline"
    assert time.monotonic() - started < 15


def test_t47_pdf_error_in_the_child_keeps_its_code() -> None:
    with pytest.raises(PdfError) as error:
        run_isolated(b"x", LIMITS, timeout_s=60, target=refuse)
    assert error.value.code == "encrypted"
