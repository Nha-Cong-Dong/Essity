"""The one way into a PPTX in ai-service (ADR-0011). Swapping the library changes only
`python_pptx_impl.py`."""

from ai_service.pptx.python_pptx_impl import PptxContent, read_pptx
from ai_service.pptx.types import MAX_TITLE_CHARS, PptxError, PptxLimits, Section, Slide

__all__ = [
    "MAX_TITLE_CHARS",
    "PptxContent",
    "PptxError",
    "PptxLimits",
    "Section",
    "Slide",
    "read_pptx",
]
