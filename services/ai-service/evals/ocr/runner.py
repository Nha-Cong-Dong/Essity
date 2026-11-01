"""OCR eval for hard images (T9.8, US-13): small text, tables, formulas written as text.

    python -m evals.ocr.runner --out docs/evals/ocr.md

Each sample image is rendered from its case (nothing binary is committed), read once by the basic
path (`shrink`, 1400 px) and once by the advanced path (`shrink(advanced=True)`, 2400 px), and the
word errors of each reading against the case text are counted: before and after. CI runs it with
the fake reader, which reads a case only when the prepared image keeps `min_side` pixels on the
long side, so the check proves the plumbing and that the advanced path keeps more pixels, not model
quality. A manual run passes a real `make_ask` (needs a key and budget; no real call is made in
the MVP build). Thresholds are not set: they are written when real data exists. The report holds
numbers and case ids only, never a text.
"""

import argparse
import io
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field

from ai_service.tasks.read_notes_image import ImageSource, ReadPrompt, read_images

DEFAULT_CASES = Path(__file__).with_name("cases.jsonl")
Ask = Callable[[ReadPrompt], str]
MakeAsk = Callable[["EvalCase"], Ask]


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    category: Literal["small_text", "table", "formula_text"]
    width: int = Field(ge=16, le=6000)
    height: int = Field(ge=16, le=6000)
    # Fake reader only: the long side the prepared image needs for the case to be read.
    min_side: int = Field(ge=1)
    text: str = Field(min_length=1)


class _NullCache:
    def get(self, key: str) -> str | None:
        return None

    def put(self, key: str, text: str) -> None:
        return None


@dataclass
class Report:
    cases: int = 0
    words: int = 0
    basic_errors: int = 0
    advanced_errors: int = 0
    by_category: dict[str, tuple[int, int]] = field(default_factory=dict[str, tuple[int, int]])
    failed: list[str] = field(default_factory=list[str])


def load_cases(path: Path) -> list[EvalCase]:
    cases = [
        EvalCase.model_validate_json(line)
        for line in path.read_text("utf-8").splitlines()
        if line.strip()
    ]
    if len({c.id for c in cases}) != len(cases):
        raise ValueError("duplicate case id")
    return cases


def render(case: EvalCase) -> bytes:
    """A white image of the case size with its text drawn on it, as PNG."""
    image = Image.new("RGB", (case.width, case.height), "white")
    ImageDraw.Draw(image).multiline_text((20, 20), case.text, fill="black")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def word_errors(expected: str, got: str) -> int:
    """Word-level edit distance (insert, delete, replace each cost 1)."""
    a, b = expected.split(), got.split()
    row = list(range(len(b) + 1))
    for i, word_a in enumerate(a, start=1):
        diagonal, row[0] = row[0], i
        for j, word_b in enumerate(b, start=1):
            cost = diagonal + (word_a != word_b)
            diagonal, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, cost)
    return row[len(b)]


def fake_make_ask(case: EvalCase) -> Ask:
    def ask(prompt: ReadPrompt) -> str:
        with Image.open(io.BytesIO(prompt.image.data)) as image:
            side = max(image.size)
        text = case.text if side >= case.min_side else " ".join(case.text.split()[:-1])
        return json.dumps({"text": text, "legible": True})

    return ask


def _errors(case: EvalCase, raw: bytes, ask: Ask, advanced: bool) -> int | None:
    result = read_images([ImageSource(1, raw)], ask, _NullCache(), advanced=advanced)
    if not result.parts:
        return None
    return word_errors(case.text, result.parts[0].text)


def run(cases: list[EvalCase], make_ask: MakeAsk = fake_make_ask) -> Report:
    """A case that cannot be read counts every word as an error, in both columns it failed."""
    report = Report()
    for case in cases:
        raw = render(case)
        ask = make_ask(case)
        words = len(case.text.split())
        basic = _errors(case, raw, ask, advanced=False)
        advanced = _errors(case, raw, ask, advanced=True)
        if basic is None or advanced is None:
            report.failed.append(case.id)
        basic = words if basic is None else basic
        advanced = words if advanced is None else advanced
        report.cases += 1
        report.words += words
        report.basic_errors += basic
        report.advanced_errors += advanced
        before, after = report.by_category.get(case.category, (0, 0))
        report.by_category[case.category] = (before + basic, after + advanced)
    return report


def render_report(report: Report, provider: str) -> str:
    lines = [
        "# OCR eval (T9.8)",
        "",
        f"provider: {provider}",
        "",
        f"- Cases: {report.cases}; words: {report.words}",
        f"- Word errors, basic path: {report.basic_errors}",
        f"- Word errors, advanced path: {report.advanced_errors}",
        f"- Cases not read: {', '.join(report.failed) or 'none'}",
        "- Threshold: not set (recorded when real data exists)",
        "",
        "| Category | Basic errors | Advanced errors |",
        "|---|---|---|",
    ]
    lines += [f"| {c} | {b} | {a} |" for c, (b, a) in sorted(report.by_category.items())]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OCR eval, fake reader (T9.8)")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = run(load_cases(args.cases))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_report(report, "fake"), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
