"""Reading the text of notes images and scanned pages by vision (T7.7, US-02 AC8/AC9).

Pure: `read_images(sources, ask, cache)` where `ask` sends a `ReadPrompt` (one image) to the model
and returns its text. The handler binds `ask` to `LlmClient` and the quota guard; tests and CI
bind it to a fake reader (the real notes model is T3.3).

- One image, one call. The cache key is the hash of the ORIGINAL bytes plus the prompt version,
  so the same image submitted again makes no second vision call, in this run or a later one.
  Only a legible, non-empty reading is cached.
- At most `MAX_IMAGES` images are read; the rest give one `truncated` entry (a neutral note, no
  count of what was lost beyond the reference of the first one left out).
- What the model returns is untrusted text. It is parsed against a closed schema and only its
  text is used, later, inside a nonce-tagged data block (`draft_units`). Nothing here logs or
  stores the text or the image; `skipped` holds a kind, a number and a fixed reason (ADR-0013).
- A page that cannot be read (bad bytes, blurred, no reply that fits the schema) is skipped alone;
  the others are still read (AC9). Quota and provider errors are the caller's: they propagate.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from ai_service.llm.types import ImagePart, Task
from ai_service.llm.vision import ImageRejected, shrink

TASK: Task = "read_notes"
PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
MAX_IMAGES = 20
MAX_IMAGE_TEXT_CHARS = 20_000
USER_LINE = "Transcribe the image."

SkipReason = Literal["no_text", "truncated", "unreadable"]


class _Reading(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    text: Annotated[str, StringConstraints(max_length=MAX_IMAGE_TEXT_CHARS)]
    legible: bool


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "legible": {"type": "boolean"},
    },
    "required": ["text", "legible"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ReadPrompt:
    system: str
    user: str
    image: ImagePart
    output_schema: dict[str, Any]


@dataclass(frozen=True)
class ImageSource:
    # 1-based position among the submission's images and scanned pages.
    ref: int
    data: bytes


@dataclass(frozen=True)
class NotePart:
    ref: int
    text: str


@dataclass(frozen=True)
class NoteSkip:
    ref: int
    reason: SkipReason


class VisionCache(Protocol):
    def get(self, key: str) -> str | None: ...

    def put(self, key: str, text: str) -> None: ...


@dataclass
class NotesRead:
    parts: list[NotePart] = field(default_factory=lambda: list[NotePart]())
    skipped: list[NoteSkip] = field(default_factory=lambda: list[NoteSkip]())
    # Calls made to the model (a cache hit makes none).
    vision_calls: int = 0


@lru_cache
def system_prompt() -> str:
    return (_PROMPTS / TASK / f"{PROMPT_VERSION}.md").read_text("utf-8")


def cache_key(raw: bytes) -> str:
    return f"{hashlib.sha256(raw).hexdigest()}-{PROMPT_VERSION}"


def read_images(
    sources: list[ImageSource], ask: Callable[[ReadPrompt], str], cache: VisionCache
) -> NotesRead:
    out = NotesRead()
    for source in sources[:MAX_IMAGES]:
        key = cache_key(source.data)
        cached = cache.get(key)
        if cached is not None:
            out.parts.append(NotePart(source.ref, cached))
            continue
        try:
            jpeg = shrink(source.data)
        except ImageRejected:
            out.skipped.append(NoteSkip(source.ref, "unreadable"))
            continue
        prompt = ReadPrompt(
            system=system_prompt(),
            user=USER_LINE,
            image=ImagePart(data=jpeg, media_type="image/jpeg"),
            output_schema=OUTPUT_SCHEMA,
        )
        out.vision_calls += 1
        try:
            reading = _Reading.model_validate(json.loads(ask(prompt)))
        except (ValidationError, ValueError):
            out.skipped.append(NoteSkip(source.ref, "unreadable"))
            continue
        if not reading.legible:
            out.skipped.append(NoteSkip(source.ref, "unreadable"))
        elif not reading.text.strip():
            out.skipped.append(NoteSkip(source.ref, "no_text"))
        else:
            cache.put(key, reading.text)
            out.parts.append(NotePart(source.ref, reading.text))
    if len(sources) > MAX_IMAGES:
        out.skipped.append(NoteSkip(sources[MAX_IMAGES].ref, "truncated"))
    return out
