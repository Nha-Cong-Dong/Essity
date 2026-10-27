"""pdf/ on PDFium through pypdfium2 (ADR-0011): one library, one parse, for all four reads.

PDFium is C code with process-wide state and is not thread-safe, even across different
documents: one thread in the whole process calls pdf/ at a time (a process per file, or a
process-wide lock). Run untrusted files in a process of their own (T4.7): the limits here
cannot stop a crash or a loop inside one page.

pypdfium2 ships no type information: the checks for unknown types are off in this module only,
and every value leaving it is converted to a typed one (str, int, bytes) first.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false

import ctypes
import io
import itertools
import math
import time
from collections.abc import Callable
from types import TracebackType
from typing import Any, Self

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from ai_service.pdf.types import (
    MAX_TITLE_CHARS,
    MIN_TEXT_CHARS,
    OutlineEntry,
    PageText,
    PdfError,
    PdfLimits,
    RenderedPage,
)

# Any failure inside the library: PdfiumError, OSError (a Windows SEH exception such as PDFium
# running out of memory), ValueError (UnicodeDecodeError of a string PDFium returned).
_LIBRARY_ERRORS = (pdfium.PdfiumError, OSError, ValueError)
# Longest bookmark title copied out of PDFium before cutting to MAX_TITLE_CHARS; a longer one
# is dropped unread (a 1 MB title shared by 1000 bookmarks exhausted PDFium's memory).
_MAX_TITLE_READ_CHARS = 4096
# A page label is a short number ("xii", "A-40"); a longer one means the labels are unusable.
_MAX_LABEL_CHARS = 128


def _read_utf16(read: Callable[[Any, int], Any], max_chars: int) -> str | None:
    """A UTF-16LE string from a PDFium "ask the size, then fill the buffer" call. None when it
    is longer than `max_chars`, decided from the size before anything is copied."""
    size = int(read(None, 0))
    if size <= 2:
        return ""
    if size > 2 * (max_chars + 1):
        return None
    buffer = ctypes.create_string_buffer(size)
    read(buffer, size)
    return buffer.raw[: size - 2].decode("utf-16-le", errors="replace")


class PdfDocument:
    """An open PDF. Use as a context manager; every read after `close` is a PdfError."""

    def __init__(self, document: pdfium.PdfDocument, page_count: int, limits: PdfLimits) -> None:
        self._document: pdfium.PdfDocument | None = document
        self._limits = limits
        self._started = time.monotonic()
        self.page_count = page_count

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._document is not None:
            self._document.close()
            self._document = None

    def get_outline(self) -> list[OutlineEntry]:
        """Bookmarks depth first, flat, `level` 0 at the top. Cut (not failed) at the entry and
        depth limits; a bookmark that loops back is followed once (PDFium tracks what it saw).
        A title too long to be one is left empty, the entry kept."""
        document = self._open()
        try:
            bookmarks = document.get_toc(max_depth=self._limits.max_outline_depth)
            entries: list[OutlineEntry] = []
            for bookmark in itertools.islice(bookmarks, self._limits.max_outline_entries):
                self._check_deadline()
                title = _read_utf16(
                    lambda buffer, size, bookmark=bookmark: pdfium_c.FPDFBookmark_GetTitle(
                        bookmark, buffer, size
                    ),
                    _MAX_TITLE_READ_CHARS,
                )
                destination = bookmark.get_dest()
                raw_index = destination.get_index() if destination is not None else None
                index = int(raw_index) if raw_index is not None else None
                entries.append(
                    OutlineEntry(
                        title=(title or "")[:MAX_TITLE_CHARS],
                        level=int(bookmark.level),
                        page_index=index if index is not None and index < self.page_count else None,
                    )
                )
            return entries
        except _LIBRARY_ERRORS as error:
            raise PdfError("malformed") from error

    def get_page_labels(self) -> list[str] | None:
        """The printed page number of each page ("ii", "A-40"); PDFium gives a page that no
        label range covers its 1-based file number. None when the printed number is unknown:
        the file has no labels, or a label too long to be a page number (PRD §7.1b: that is
        not the same as "1, 2, 3")."""
        document = self._open()
        labels: list[str] = []
        try:
            for index in range(self.page_count):
                self._check_deadline()
                label = _read_utf16(
                    lambda buffer, size, index=index: pdfium_c.FPDF_GetPageLabel(
                        document, index, buffer, size
                    ),
                    _MAX_LABEL_CHARS,
                )
                if label is None:
                    return None
                labels.append(label)
        except _LIBRARY_ERRORS as error:
            raise PdfError("malformed") from error
        return labels if any(labels) else None

    def extract_text(self, index: int) -> PageText:
        page = self._page(index)
        try:
            textpage = page.get_textpage()
            try:
                count = min(textpage.count_chars(), self._limits.max_text_chars_per_page)
                text = str(textpage.get_text_range(0, count)) if count > 0 else ""
            finally:
                textpage.close()
        except _LIBRARY_ERRORS as error:
            raise PdfError("malformed") from error
        finally:
            page.close()
        text = text[: self._limits.max_text_chars_per_page]
        visible = sum(1 for char in text if not char.isspace())
        return PageText(text=text, needs_vision=visible < MIN_TEXT_CHARS)

    def render_page(self, index: int, *, max_px: int) -> RenderedPage:
        """PNG of the page with its long side at `max_px` (capped by the limits), sized from
        the page box before rendering so a giant or tiny MediaBox cannot blow up memory."""
        page = self._page(index)
        try:
            width, height = float(page.get_width()), float(page.get_height())
            if not (math.isfinite(width) and math.isfinite(height)) or width <= 0 or height <= 0:
                raise PdfError("malformed")
            scale = self._scale(width, height, max_px)
            # pypdfium2 infers `scale: int` from its default; any float is valid.
            bitmap = page.render(scale=scale, may_draw_forms=False)  # pyright: ignore[reportArgumentType]
            try:
                image = bitmap.to_pil()
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                rendered = RenderedPage(
                    png=buffer.getvalue(), width=int(image.width), height=int(image.height)
                )
            finally:
                bitmap.close()
        except _LIBRARY_ERRORS as error:
            raise PdfError("malformed") from error
        finally:
            page.close()
        return rendered

    def _scale(self, width: float, height: float, max_px: int) -> float:
        long_side, short_side = max(width, height), min(width, height)
        budget = self._limits.max_render_pixels
        target = min(max_px, self._limits.max_render_px)
        target = max(1, min(target, math.floor(math.sqrt(budget * long_side / short_side))))
        # pypdfium2 sizes the bitmap as ceil(side * scale); stay a hair under the target so
        # float error never adds a pixel, then step down until the pixel budget holds.
        while True:
            scale = target * (1 - 1e-9) / long_side
            pixels = math.ceil(long_side * scale) * math.ceil(short_side * scale)
            if target == 1 or pixels <= budget:
                return scale
            target -= 1

    def _check_deadline(self) -> None:
        if time.monotonic() - self._started >= self._limits.deadline_s:
            raise PdfError("deadline")

    def _open(self) -> pdfium.PdfDocument:
        if self._document is None:
            raise PdfError("closed")
        return self._document

    def _page(self, index: int) -> pdfium.PdfPage:
        document = self._open()
        if not 0 <= index < self.page_count:
            raise PdfError("page_out_of_range")
        self._check_deadline()
        try:
            return document[index]
        except _LIBRARY_ERRORS as error:
            raise PdfError("malformed") from error


def open_pdf(data: bytes, *, limits: PdfLimits | None = None) -> PdfDocument:
    """Open a PDF held in memory. Raises PdfError: too_large, malformed, encrypted (a
    password is needed to open it; an owner-only password is not), too_many_pages."""
    limits = limits or PdfLimits()
    if len(data) > limits.max_bytes:
        raise PdfError("too_large")
    if not data:
        raise PdfError("malformed")
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as error:
        # PDFium keeps its previous error when a load fails without setting one, so a
        # password error alone may be stale; an encrypted file always names /Encrypt in its
        # trailer, which is never compressed.
        if error.err_code == pdfium_c.FPDF_ERR_PASSWORD and b"/Encrypt" in data:
            raise PdfError("encrypted") from error
        raise PdfError("malformed") from error
    except _LIBRARY_ERRORS as error:
        raise PdfError("malformed") from error
    page_count = int(len(document))
    if page_count == 0 or page_count > limits.max_pages:
        document.close()
        raise PdfError("malformed" if page_count == 0 else "too_many_pages")
    return PdfDocument(document, page_count, limits)
