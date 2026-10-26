"""The seed file of `seed-questions` (T2.2): one chapter of units and the questions that check
them, written by hand in YAML. Validated whole before anything is written; an error names the
line it is on.

```yaml
units:
  - title: Bắt tay ba bước
    summary: TCP mở kết nối bằng SYN, SYN-ACK, ACK.
    kind: concept            # concept | mechanism | comparison | formula | example
    sources:                 # where the unit comes from (anchor), at least one
      - source: document     # document | notes
        page: 4              # optional
        quote: TCP thiết lập kết nối bằng bắt tay ba bước.
questions:
  - level: 1                 # 1..3
    prompt: TCP mở kết nối như thế nào?
    answer: Bằng bắt tay ba bước.
    units: [Bắt tay ba bước] # titles of units of this file
```
"""

from typing import Annotated, Any, Literal, cast

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    StringConstraints,
    ValidationError,
)

from core_api.api.text import storable_answer

# Lines and tabs are kept (an answer has paragraphs); NUL and lone surrogates are refused.
SeedText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
    AfterValidator(storable_answer),
]
Kind = Literal["concept", "mechanism", "comparison", "formula", "example"]
Source = Literal["document", "notes"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SeedSource(_Strict):
    source: Source
    quote: SeedText
    page: Annotated[int, Field(ge=1)] | None = None


class SeedUnit(_Strict):
    title: Annotated[SeedText, Field(max_length=200)]
    summary: SeedText
    kind: Kind
    sources: Annotated[list[SeedSource], Field(min_length=1)]


class SeedQuestion(_Strict):
    level: Annotated[int, Field(ge=1, le=3)]
    prompt: SeedText
    answer: SeedText
    units: Annotated[list[str], Field(min_length=1)]


class SeedFile(_Strict):
    units: Annotated[list[SeedUnit], Field(min_length=1)]
    questions: Annotated[list[SeedQuestion], Field(min_length=1)]
    # The line each question starts on, for messages about it after parsing.
    _lines: list[int] = PrivateAttr(default_factory=list[int])

    @property
    def question_lines(self) -> list[int]:
        return self._lines


class SeedFileError(ValueError):
    """The file cannot be loaded; `problems` are lines ready to print."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _line_of(node: yaml.Node | None, path: tuple[str | int, ...]) -> int:
    """The line (1-based) of the node at `path`, or of the deepest one that exists."""
    line = 1 if node is None else node.start_mark.line + 1
    for step in path:
        if isinstance(node, yaml.MappingNode):
            found = None
            for key, value in node.value:
                if key.value == step:
                    found = value
                    line = key.start_mark.line + 1
                    break
            node = found
        elif isinstance(node, yaml.SequenceNode) and isinstance(step, int):
            node = node.value[step] if step < len(node.value) else None
            if node is not None:
                line = node.start_mark.line + 1
        else:
            break
        if node is None:
            break
    return line


def parse(text: str) -> SeedFile:
    try:
        root = cast(
            "yaml.Node | None",
            yaml.compose(text),  # pyright: ignore[reportUnknownMemberType]
        )
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 1 if mark is not None else 1
        raise SeedFileError([f"line {line}: not valid YAML"]) from error
    try:
        seed = SeedFile.model_validate(data)
    except ValidationError as error:
        raise SeedFileError(
            [
                f"line {_line_of(root, tuple(e['loc']))}: "
                f"{'.'.join(str(p) for p in e['loc']) or 'file'}: {e['msg']}"
                for e in error.errors()
            ]
        ) from error
    problems: list[str] = []
    titles = [unit.title for unit in seed.units]
    for index, title in enumerate(titles):
        if titles.index(title) != index:
            line = _line_of(root, ("units", index, "title"))
            problems.append(f"line {line}: units.{index}.title: duplicate unit title")
    for q_index, question in enumerate(seed.questions):
        for u_index, name in enumerate(question.units):
            if name not in titles:
                line = _line_of(root, ("questions", q_index, "units"))
                problems.append(
                    f"line {line}: questions.{q_index}.units.{u_index}: no unit {name!r}"
                )
    if problems:
        raise SeedFileError(problems)
    seed._lines = [  # pyright: ignore[reportPrivateUsage]
        _line_of(root, ("questions", n)) for n in range(len(seed.questions))
    ]
    return seed
