"""T7.7 / US-02 AC8, ADR-0013 (tester): the pixel budget is checked on the header, before any
pixel is decoded (review Y-b, point 1).

The existing bomb test lowers `MAX_PIXELS` and feeds a small, complete PNG: it stays green if the
check is moved after `image.load()`. Here the PNG header claims a canvas over the real budget and
the pixel data is cut short, so decoding it fails; only a check made BEFORE loading answers
`too_many_pixels`. Last test: the cache key follows the prompt version."""

import io
import struct
import zlib

import pytest
from PIL import Image, ImageFile

from ai_service.llm import vision
from ai_service.llm.vision import ImageRejected, shrink


def _bomb_header(width: int, height: int) -> bytes:
    """A real small PNG whose IHDR is rewritten to `width` x `height` (CRC fixed), its IDAT
    left as is: the header says a huge canvas, the data is a few bytes."""
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(out, format="PNG")
    data = bytearray(out.getvalue())
    ihdr = data.index(b"IHDR")
    struct.pack_into(">II", data, ihdr + 4, width, height)
    crc = zlib.crc32(bytes(data[ihdr : ihdr + 17]))
    struct.pack_into(">I", data, ihdr + 17, crc)
    return bytes(data)


def test_adr13_bomb_header_with_truncated_data_is_too_many_pixels_not_decoded() -> None:
    # Red when: the pixel check runs after image.load() (decoding the cut data fails first and the
    # code becomes not_an_image), or the check is dropped.
    side = 7_000  # 49 M pixels: over MAX_PIXELS (40 M), under Pillow's own bomb guard
    assert side * side > vision.MAX_PIXELS
    with pytest.raises(ImageRejected) as error:
        shrink(_bomb_header(side, side))
    assert error.value.code == "too_many_pixels"


def test_adr13_no_pixel_is_loaded_for_an_image_over_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: image.load() (or anything that decodes) runs before the pixel budget check.
    loads: list[str] = []
    real_load = ImageFile.ImageFile.load

    def counting_load(self: ImageFile.ImageFile) -> object:
        loads.append(self.format or "?")
        return real_load(self)

    monkeypatch.setattr(ImageFile.ImageFile, "load", counting_load)
    monkeypatch.setattr(vision, "MAX_PIXELS", 10_000)
    out = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(out, format="PNG")
    with pytest.raises(ImageRejected) as error:
        shrink(out.getvalue())
    assert error.value.code == "too_many_pixels"
    assert loads == []


def test_us02_ac8_a_new_prompt_version_reads_the_image_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: the vision cache key drops the prompt version: after a prompt change the old
    # reading (made under other rules) is served forever and never read again.
    from ai_service.tasks import read_notes_image

    raw = b"same image bytes"
    before = read_notes_image.cache_key(raw)
    monkeypatch.setattr(read_notes_image, "PROMPT_VERSION", "v2")
    assert read_notes_image.cache_key(raw) != before
