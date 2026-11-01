"""Preparing an image for a vision call (T7.7, US-02 AC8).

`shrink` is the only way an image reaches the model: decoded as JPEG or PNG only, refused above a
pixel budget before it is loaded, turned upright by its EXIF tag, flattened to RGB, cut to
`MAX_LONG_SIDE` on the long side and re-encoded as JPEG without any metadata (location, device).
A refusal carries a fixed code, never the library's text.
"""

import io
from typing import Literal

from PIL import Image, ImageOps

MAX_LONG_SIDE = 1400
# The advanced path (T9.8: small text, tables, text formulas) keeps more pixels and a better JPEG.
ADVANCED_LONG_SIDE = 2400
ADVANCED_JPEG_QUALITY = 92
MAX_PIXELS = 40_000_000
MAX_BYTES = 15_000_000
JPEG_QUALITY = 85
ImageErrorCode = Literal["too_large", "not_an_image", "too_many_pixels"]


class ImageRejected(Exception):
    """The bytes are not an image we read. `code` is stable and safe to log."""

    def __init__(self, code: ImageErrorCode) -> None:
        super().__init__(code)
        self.code: ImageErrorCode = code


def shrink(data: bytes, *, advanced: bool = False) -> bytes:
    """JPEG bytes of the image, long side at most `MAX_LONG_SIDE` (`ADVANCED_LONG_SIDE` when
    `advanced`: the same checks and refusals, more pixels kept, contrast stretched)."""
    if len(data) > MAX_BYTES:
        raise ImageRejected("too_large")
    try:
        with Image.open(io.BytesIO(data), formats=("JPEG", "PNG")) as image:
            width, height = image.size
            if width * height > MAX_PIXELS:
                raise ImageRejected("too_many_pixels")
            image.load()
            upright = ImageOps.exif_transpose(image)
            rgb = _flatten(upright)
    except ImageRejected:
        raise
    except Exception:  # Pillow's own errors name the file; the code is enough
        raise ImageRejected("not_an_image") from None
    side = ADVANCED_LONG_SIDE if advanced else MAX_LONG_SIDE
    rgb.thumbnail((side, side), Image.Resampling.LANCZOS)
    if advanced:
        rgb = ImageOps.autocontrast(rgb)
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=ADVANCED_JPEG_QUALITY if advanced else JPEG_QUALITY)
    return out.getvalue()


def _flatten(image: Image.Image) -> Image.Image:
    """RGB on a white ground: a transparent PNG must not turn black."""
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        ground = Image.new("RGB", rgba.size, "white")
        ground.paste(rgba, mask=rgba.getchannel("A"))
        return ground
    return image.convert("RGB")
