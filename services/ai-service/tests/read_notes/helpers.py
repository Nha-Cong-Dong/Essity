"""Pieces for the notes-image tests: real small images, a counting fake reader, a dict cache."""

import io
import json

from PIL import Image

from ai_service.tasks.read_notes_image import ReadPrompt


def png(width: int = 200, height: int = 100, colour: str = "white", fmt: str = "PNG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, format=fmt)
    return out.getvalue()


def png_n(n: int, size: int = 100) -> bytes:
    """An image different for each `n` (so a different hash)."""
    out = io.BytesIO()
    Image.new("RGB", (size, size), (n % 256, n // 256, 7)).save(out, format="PNG")
    return out.getvalue()


class DictCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def put(self, key: str, text: str) -> None:
        self.store[key] = text


class Reader:
    """Answers every call with one reading and keeps the prompts it received."""

    def __init__(self, text: str = "Mitochondria make ATP by respiration.", legible: bool = True):
        self.text, self.legible = text, legible
        self.prompts: list[ReadPrompt] = []

    def __call__(self, prompt: ReadPrompt) -> str:
        self.prompts.append(prompt)
        return json.dumps({"text": self.text, "legible": self.legible})

    @property
    def calls(self) -> int:
        return len(self.prompts)
