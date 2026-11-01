"""T9.8 / US-13 (hard images for the notes reader; US-02 AC8 caps reused): the advanced path
keeps more pixels, has its own cache key and the same page limit with a neutral note."""

import io

from PIL import Image

from ai_service.llm.vision import ADVANCED_LONG_SIDE, MAX_LONG_SIDE, ImageRejected, shrink
from ai_service.tasks.read_notes_image import (
    MAX_IMAGES,
    ImageSource,
    NoteSkip,
    cache_key,
    read_images,
)
from tests.read_notes.helpers import DictCache, Reader, png, png_n


def size_of(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


def test_advanced_shrink_keeps_more_pixels_than_the_default() -> None:
    big = png(4000, 3000)
    assert max(size_of(shrink(big))) == MAX_LONG_SIDE
    assert max(size_of(shrink(big, advanced=True))) == ADVANCED_LONG_SIDE > MAX_LONG_SIDE
    assert size_of(shrink(png(300, 200), advanced=True)) == (300, 200)


def test_advanced_shrink_keeps_the_same_refusals() -> None:
    for advanced in (False, True):
        try:
            shrink(b"not an image", advanced=advanced)
        except ImageRejected as error:
            assert error.code == "not_an_image"
        else:
            raise AssertionError("accepted")


def test_advanced_cache_key_differs_from_the_default() -> None:
    raw = png_n(1)
    assert cache_key(raw, advanced=True) != cache_key(raw)
    assert cache_key(raw) == cache_key(raw, advanced=False)


def test_advanced_reading_does_not_reuse_the_default_cache_entry() -> None:
    cache, reader = DictCache(), Reader()
    src = [ImageSource(1, png_n(2))]
    read_images(src, reader, cache)
    again = read_images(src, reader, cache, advanced=True)
    assert reader.calls == 2 and again.vision_calls == 1
    third = read_images(src, reader, cache, advanced=True)
    assert reader.calls == 2 and third.vision_calls == 0


def test_advanced_prompt_carries_a_hard_image_instruction_and_the_big_image() -> None:
    reader = Reader()
    read_images([ImageSource(1, png(4000, 3000))], reader, DictCache(), advanced=True)
    prompt = reader.prompts[0]
    assert "table" in prompt.user.lower() and "formula" in prompt.user.lower()
    assert max(size_of(prompt.image.data)) == ADVANCED_LONG_SIDE


def test_over_limit_images_read_first_n_and_one_neutral_note() -> None:  # US-02 AC8 reuse
    reader = Reader()
    sources = [ImageSource(i + 1, png_n(i)) for i in range(MAX_IMAGES + 3)]
    out = read_images(sources, reader, DictCache(), advanced=True)
    assert reader.calls == MAX_IMAGES and len(out.parts) == MAX_IMAGES
    assert out.skipped == [NoteSkip(MAX_IMAGES + 1, "truncated")]
