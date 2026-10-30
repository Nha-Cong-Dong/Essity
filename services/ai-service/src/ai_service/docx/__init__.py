"""The one way into a DOCX in ai-service (ADR-0011). Swapping the library changes only
`python_docx_impl.py`."""

from ai_service.docx.python_docx_impl import DocxContent, read_docx
from ai_service.docx.types import (
    MAX_HEADING_LEVEL,
    MAX_TITLE_CHARS,
    DocxError,
    DocxLimits,
    Paragraph,
)

__all__ = [
    "MAX_HEADING_LEVEL",
    "MAX_TITLE_CHARS",
    "DocxContent",
    "DocxError",
    "DocxLimits",
    "Paragraph",
    "read_docx",
]
