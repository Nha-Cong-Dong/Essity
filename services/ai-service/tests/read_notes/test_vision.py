"""T7.7 / US-02 AC8: an image is cut to 1400 px on the long side; anything else is refused."""

import io

import pytest
from PIL import Image

from ai_service.llm import vision
from ai_service.llm.vision import ImageRejected, shrink
from tests.read_notes.helpers import png


def size_of(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


def test_us02_ac8_shrink_long_side_le_1400_keeps_small() -> None:
    # Red when: a big photo goes to the model uncut, or a small one is upscaled.
    assert max(size_of(shrink(png(4000, 3000)))) == 1400
    assert size_of(shrink(png(300, 200))) == (300, 200)


def test_us02_ac8_shrink_keeps_the_aspect_and_makes_a_jpeg() -> None:
    out = shrink(png(2800, 1400))
    assert size_of(out) == (1400, 700)
    assert out[:2] == b"\xff\xd8"


def test_us02_ac8_shrink_accepts_jpeg_input() -> None:
    assert size_of(shrink(png(2000, 1000, fmt="JPEG"))) == (1400, 700)


def test_us02_ac8_shrink_drops_exif_and_turns_the_image_upright() -> None:
    # Red when: the location/device tags stay in what is sent, or a phone photo is sideways.
    image = Image.new("RGB", (400, 200), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 clockwise to view
    exif[0x010F] = "SecretMaker"
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    out = shrink(buf.getvalue())
    assert size_of(out) == (200, 400)
    assert b"SecretMaker" not in out
    assert not Image.open(io.BytesIO(out)).getexif()


def test_us02_ac8_transparent_png_goes_on_white() -> None:
    buf = io.BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(buf, format="PNG")
    pixel = Image.open(io.BytesIO(shrink(buf.getvalue()))).getpixel((10, 10))
    assert isinstance(pixel, tuple) and min(pixel) > 240


@pytest.mark.parametrize("junk", [b"", b"not an image at all", b"GIF89a" + b"\0" * 30, b"%PDF-1.7"])
def test_us02_ac8_shrink_rejects_non_image_bytes(junk: bytes) -> None:
    with pytest.raises(ImageRejected) as error:
        shrink(junk)
    assert error.value.code == "not_an_image"


def test_us02_ac8_shrink_rejects_a_real_gif() -> None:
    gif = io.BytesIO()
    Image.new("P", (10, 10)).save(gif, format="GIF")
    with pytest.raises(ImageRejected):
        shrink(gif.getvalue())


def test_adr13_shrink_rejects_a_pixel_bomb_before_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    # Red when: a huge canvas is decoded (memory) with only Pillow's own 2x limit as a guard.
    monkeypatch.setattr(vision, "MAX_PIXELS", 10_000)
    with pytest.raises(ImageRejected) as error:
        shrink(png(200, 100))
    assert error.value.code == "too_many_pixels"


def test_shrink_rejects_a_file_over_the_byte_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vision, "MAX_BYTES", 10)
    with pytest.raises(ImageRejected) as error:
        shrink(png())
    assert error.value.code == "too_large"
