"""Question bank core (T8.1a, US-14): split a bank into questions, group them into types, link
them to syllabus sections.

Everything here is pure: `ask` sends a `BankPrompt` to the model and returns its text. Binding
`ask` to `LlmClient` and the quota guard, the llm `Task` literal and pricing row, the event path,
the DB writes and `content_hash` dedupe (AC8) are T8.1b's work.

Three steps, each returns a result with `status` and `reasons` instead of raising:
  1. `split_bank`: numbering found by regex ("Câu N", "N.", "Question N", "QN") splits pages with
     no model call; the model reads only the pages before the first numbered one, or all pages
     when no numbering style yields two markers. A question or answer the model returns is kept
     only as the span of the page text it matches (the code checks, like anchor_check), so the
     bank's own words are never altered (AC1). The model never writes an answer.
  2. `suggest_types`: at most `MAX_TYPES` names per bank, existing names reused (AC2).
  3. `map_sections`: the model sees labels S1..Sn, never ids; an unknown label is dropped and a
     question left without a section is `unmapped` (AC3).

`status`: `pending_ai` when the quota stopped the work (AC9: the caller queues the job again),
`partial` when something was dropped or a call failed, else `done`. Model output is untrusted:
size and schema checked, any failure keeps what was verified. Nothing here logs a question,
answer or title.
"""

import hashlib
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from ai_service.domain.anchor_check import Span, normalize_with_map, unescape_quote
from ai_service.llm.quota import QuotaExceededError
from ai_service.pdf import PageText
from ai_service.tasks.grade import new_nonce, wrap_untrusted

_log = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"
ATTEMPTS = 2
MAX_OUTPUT_CHARS = 100_000
MAX_QUESTIONS = 500
MAX_TEXT_CHARS = 4000  # one prompt or one answer
MAX_QUOTE_CHARS = 300
MAX_PAGE_CHARS = 12_000
PAGES_PER_CALL = 5
MAX_LLM_PAGES = 40
CHUNK_QUESTIONS = 40
MAX_TYPES = 12
MAX_TYPE_NAME_CHARS = 80
MAX_EXISTING_TYPES = 50
MAX_SECTIONS = 500
MAX_SECTION_TITLE_CHARS = 200
MAX_SECTIONS_PER_QUESTION = 5
MAX_QUESTION_CHARS_IN_PROMPT = 600
# Shorter text proves nothing when it is looked up in a page.
_MIN_MATCH_CHARS = 4

Status = Literal["done", "partial", "pending_ai"]
_INFO_CODES = frozenset({"no_syllabus"})

# Each style: the number in group 1, what is left of the line in group 2. "Câu" may be typed
# with or without the circumflex.
_STYLES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*c[âa]u\s+(\d{1,4})\s*[.:)\-]?\s*(.*)$", re.I),
    re.compile(r"^\s*question\s+(\d{1,4})\s*[.:)\-]?\s*(.*)$", re.I),
    re.compile(r"^\s*q(\d{1,4})\s*[.:)]\s*(.*)$", re.I),
    re.compile(r"^\s*(\d{1,4})\s*[.)]\s+(.*)$"),
)
# A marker may skip a number or two (a garbled line) but never goes back, so "1. A  2. B" in an
# answer key after question 10 is not a question.
_MAX_SKIP = 3
_ANSWER = re.compile(r"^\s*(?:đáp\s*án|answer|trả\s*lời|lời\s*giải)\s*[:.)\-]\s*(.*)$", re.I)


# A heading alone on its line that starts the answers or an appendix.
_SECTION_BREAK = re.compile(
    r"^\s*(?:đáp\s*án|answer\s*key|answers|lời\s*giải|phụ\s*lục|appendix)\s*:?\s*$", re.I
)


@dataclass(frozen=True)
class Reason:
    code: str
    ref: str = ""


@dataclass(frozen=True)
class Question:
    ord: int  # 1-based, in order of appearance
    prompt: str
    # The bank's own answer, as the source wrote it; None when the bank gives none (T8.4 drafts).
    answer_text: str | None
    source_page: int  # 1-based
    quote: str


@dataclass(frozen=True)
class Section:
    id: str
    title: str


@dataclass(frozen=True)
class BankPrompt:
    system: str
    user: str
    output_schema: dict[str, Any]
    nonce: str


@dataclass(frozen=True)
class SplitResult:
    questions: list[Question]
    reasons: list[Reason]
    status: Status


@dataclass(frozen=True)
class TypesResult:
    assignment: dict[int, str]  # question ord -> type name
    types: list[str]  # first-appearance order, at most MAX_TYPES
    untyped: list[int]
    reasons: list[Reason]
    status: Status


@dataclass(frozen=True)
class SectionsResult:
    mapping: dict[int, list[str]]  # question ord -> section ids
    unmapped: list[int]  # shown later as "chưa gắn được mục"
    reasons: list[Reason]
    status: Status


Ask = Callable[[BankPrompt], str]


# ---- schemas and prompts ---------------------------------------------------------------------


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise ValueError("NUL")
    return text


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("blank")
    return text


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


_Label = Annotated[str, Field(max_length=8)]
_Text = Annotated[
    str, AfterValidator(_no_nul), AfterValidator(_not_blank), Field(max_length=MAX_TEXT_CHARS)
]


class LlmQuestion(_Strict):
    page: _Label
    prompt: _Text
    answer: Annotated[str, AfterValidator(_no_nul), Field(max_length=MAX_TEXT_CHARS)] | None


class LlmSplit(_Strict):
    questions: Annotated[list[LlmQuestion], Field(max_length=200)]


class LlmType(_Strict):
    name: Annotated[
        str,
        AfterValidator(_no_nul),
        AfterValidator(_not_blank),
        Field(max_length=MAX_TYPE_NAME_CHARS),
    ]
    questions: Annotated[list[_Label], Field(max_length=CHUNK_QUESTIONS)]


class LlmTypes(_Strict):
    types: Annotated[list[LlmType], Field(max_length=MAX_TYPES * 3)]


class LlmMapping(_Strict):
    question: _Label
    sections: Annotated[list[_Label], Field(max_length=20)]


class LlmMappings(_Strict):
    mappings: Annotated[list[LlmMapping], Field(max_length=CHUNK_QUESTIONS * 2)]


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str
    sha256: str


@lru_cache
def load_prompt(name: str, version: str = PROMPT_VERSION) -> Prompt:
    text = (_PROMPTS / name / f"{version}.md").read_text("utf-8")
    return Prompt(name, version, text, hashlib.sha256(text.encode()).hexdigest())


def _build(
    name: str, schema: type[BaseModel], parts: Sequence[tuple[str, str, str | None]]
) -> BankPrompt:
    """`parts`: (kind, untrusted text, label). One fresh nonce that appears in none of them."""
    nonce = new_nonce()
    while any(nonce in text for _, text, _ in parts):
        nonce = new_nonce()
    blocks = [
        wrap_untrusted(kind, text, nonce, **({"label": label} if label else {}))
        for kind, text, label in parts
    ]
    system = load_prompt(name).text.replace(_NONCE_PLACEHOLDER, nonce)
    return BankPrompt(system, "\n\n".join(blocks), schema.model_json_schema(), nonce)


def _call[M: BaseModel](
    ask: Ask, prompt: BankPrompt, model: type[M], reasons: list[Reason], ref: str
) -> M | None:
    """Parsed output, or None with a reason. Quota is the one error that passes through."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            text = ask(prompt)
        except QuotaExceededError:
            raise
        except Exception as error:  # provider, network: the type only, never a message
            _log.warning(
                "question bank call failed",
                extra={"outcome": type(error).__name__, "attempt": attempt},
            )
            reasons.append(Reason("llm_failed", ref))
            return None
        try:
            if len(text) > MAX_OUTPUT_CHARS:
                raise ValueError("too_long")
            return model.model_validate_json(text)
        except (ValidationError, ValueError):
            _log.warning("question bank output refused", extra={"attempt": attempt})
    reasons.append(Reason("malformed_output", ref))
    return None


def _status(reasons: Sequence[Reason], pending: bool) -> Status:
    if pending:
        return "pending_ai"
    return "partial" if any(r.code not in _INFO_CODES for r in reasons) else "done"


def _single_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _span(
    text: str, quote: str, *, start: int = 0, min_chars: int = _MIN_MATCH_CHARS
) -> Span | None:
    """The span of `text` (offsets into the original, at or after `start`) that equals `quote`
    after NFC and whitespace folding; None when absent. The model copies what it was shown, so
    `& < >` come back escaped and are undone first. A match shorter than `_MIN_MATCH_CHARS`
    must stand alone as a word."""
    needle = normalize_with_map(unescape_quote(quote))[0].strip()
    if len(needle) < min_chars or "\x00" in needle:
        return None
    haystack, spans = normalize_with_map(text)
    at = haystack.find(
        needle, next((k for k, (a, _) in enumerate(spans) if a >= start), len(haystack))
    )
    while at >= 0:
        end = at + len(needle)
        alone = (at == 0 or not haystack[at - 1].isalnum()) and (
            end == len(haystack) or not haystack[end].isalnum()
        )
        if len(needle) >= _MIN_MATCH_CHARS or alone:
            return spans[at][0], spans[end - 1][1]
        at = haystack.find(needle, at + 1)
    return None


# ---- split_bank ------------------------------------------------------------------------------

_Line = tuple[int, str]  # (0-based page, text)
_Marker = tuple[int, int, str]  # (line index, number, rest of the line)


def _markers(lines: Sequence[_Line], style: re.Pattern[str]) -> list[_Marker]:
    found: list[_Marker] = []
    last: int | None = None
    for index, (_, line) in enumerate(lines):
        match = style.match(line)
        if not match:
            continue
        number = int(match.group(1))
        if last is None or last < number <= last + _MAX_SKIP:
            found.append((index, number, match.group(2)))
            last = number
    return found


def _is_appendix(lines: Sequence[_Line], n: int) -> bool:
    """Whether the heading on line `n` starts an answer key: a bank before it, a numbering
    restarting at 1 after it, and no numbering of the bank going on after it."""
    before = [_markers(lines[:n], style) for style in _STYLES]
    after = [_markers(lines[n + 1 :], style) for style in _STYLES]
    if not any(len(m) >= 2 for m in before):
        return False
    if not any(len(m) >= 2 and m[0][1] == 1 for m in after):
        return False
    for b, a in zip(before, after, strict=True):
        if b and a and b[-1][1] < a[0][1] <= b[-1][1] + _MAX_SKIP:
            return False
    return True


def _regex_split(pages: Sequence[PageText]) -> tuple[list[Question], list[Reason], int]:
    """Questions from the numbering, and the 0-based index of the first page those cover (pages
    before it were not split). `len(pages)` when no style gives two markers."""
    lines: list[_Line] = [
        (p, line) for p, page in enumerate(pages) for line in page.text.splitlines()
    ]
    full = [_markers(lines, style) for style in _STYLES]
    best = max(full, key=len)
    # An answer key or appendix heading ends the questions: its own numbering ("1. B 2. C")
    # must not count as questions or swallow the last one. A heading is a cut only when what
    # follows it restarts numbering at 1 in some style (two markers or more) and no style of the
    # part before it carries on past the heading ("Lời giải:" alone on a line is one question's
    # answer, and the next "Câu k" continues). Unclear: no cut, everything is kept. The style is
    # then chosen from the part before the cut. The first cut heading wins.
    for n, (_, line) in enumerate(lines):
        if _SECTION_BREAK.match(line) and _is_appendix(lines, n):
            lines = lines[:n]
            best = max((_markers(lines, style) for style in _STYLES), key=len)
            break
    if len(best) < 2:
        return [], [], len(pages)
    questions: list[Question] = []
    reasons: list[Reason] = []
    for k, (start, number, rest) in enumerate(best):
        end = best[k + 1][0] if k + 1 < len(best) else len(lines)
        body = [rest, *(line for _, line in lines[start + 1 : end])]
        last = k + 1 == len(best)
        prompt_lines: list[str] = []
        answer_lines: list[str] | None = None
        for line in body:
            answer = _ANSWER.match(line) if answer_lines is None else None
            if answer:
                answer_lines = [answer.group(1)]
            elif answer_lines is None:
                prompt_lines.append(line)
            else:
                answer_lines.append(line)
        prompt = "\n".join(s for line in prompt_lines if (s := line.strip()))
        answer = "\n".join(s for line in answer_lines or [] if (s := line.strip())) or None
        page = lines[start][0]
        if last and (len(prompt) > MAX_TEXT_CHARS or len(answer or "") > MAX_TEXT_CHARS):
            prompt, answer = prompt[:MAX_TEXT_CHARS], (answer or "")[:MAX_TEXT_CHARS] or None
            reasons.append(Reason("tail_capped", f"page_{page + 1}"))
        if not prompt:
            reasons.append(Reason("empty_prompt", f"page_{page + 1}"))
        elif len(prompt) > MAX_TEXT_CHARS or len(answer or "") > MAX_TEXT_CHARS:
            reasons.append(Reason("too_long", f"page_{page + 1}"))
        else:
            questions.append(Question(number, prompt, answer, page + 1, prompt[:MAX_QUOTE_CHARS]))
    return questions, reasons, lines[best[0][0]][0]


def _llm_split(
    pages: Sequence[PageText], indexes: Sequence[int], ask: Ask, reasons: list[Reason]
) -> list[Question]:
    """Raises QuotaExceededError; the caller keeps what it has."""
    found: list[Question] = []
    wanted = [i for i in indexes if pages[i].text.strip()]
    if len(wanted) > MAX_LLM_PAGES:
        reasons.append(Reason("pages_skipped", f"{len(wanted) - MAX_LLM_PAGES}"))
        wanted = wanted[:MAX_LLM_PAGES]
    for at in range(0, len(wanted), PAGES_PER_CALL):
        batch = {f"P{n}": i for n, i in enumerate(wanted[at : at + PAGES_PER_CALL], start=1)}
        parts = [("page", pages[i].text[:MAX_PAGE_CHARS], label) for label, i in batch.items()]
        prompt = _build("bank_split", LlmSplit, parts)
        parsed = _call(ask, prompt, LlmSplit, reasons, f"pages_{at + 1}")
        if parsed is None:
            continue
        for item in parsed.questions:
            index = batch.get(item.page)
            if index is None:
                reasons.append(Reason("unknown_page"))
                continue
            source = pages[index].text[:MAX_PAGE_CHARS]
            where = _span(source, item.prompt)
            if where is None:
                reasons.append(Reason("prompt_not_in_source", f"page_{index + 1}"))
                continue
            answer_text = None
            if item.answer is not None and item.answer.strip():
                # After the question, on its page or the pages that follow in this batch, so a
                # one-word answer ("Sai", "B") is still the bank's.
                later = [pages[i].text[:MAX_PAGE_CHARS] for i in batch.values() if i > index]
                for text, start in [(source, where[1]), *((t, 0) for t in later)]:
                    if (hit := _span(text, item.answer, start=start, min_chars=1)) is not None:
                        answer_text = text[hit[0] : hit[1]]
                        break
                if answer_text is None:
                    reasons.append(Reason("answer_not_in_source", f"page_{index + 1}"))
            prompt_text = source[where[0] : where[1]]
            found.append(
                Question(0, prompt_text, answer_text, index + 1, prompt_text[:MAX_QUOTE_CHARS])
            )
    return found


def split_bank(pages: Sequence[PageText], ask: Ask) -> SplitResult:
    """Questions of one bank, in page order. Never raises for what the file or the model holds."""
    reasons: list[Reason] = []
    questions, reasons_regex, first = _regex_split(pages)
    reasons.extend(reasons_regex)
    pending = False
    try:
        questions += _llm_split(pages, range(first), ask, reasons)
    except QuotaExceededError:
        pending = True
    questions.sort(key=lambda q: q.source_page)  # stable: the order within a page is kept
    if len(questions) > MAX_QUESTIONS:
        reasons.append(Reason("too_many", f"{len(questions)}"))
        questions = questions[:MAX_QUESTIONS]
    numbered = [
        Question(n, q.prompt, q.answer_text, q.source_page, q.quote)
        for n, q in enumerate(questions, start=1)
    ]
    return SplitResult(numbered, reasons, _status(reasons, pending))


# ---- suggest_types ---------------------------------------------------------------------------


def _chunks(questions: Sequence[Question]) -> list[list[tuple[str, Question]]]:
    labelled = [(f"Q{n}", q) for n, q in enumerate(questions, start=1)]
    return [labelled[i : i + CHUNK_QUESTIONS] for i in range(0, len(labelled), CHUNK_QUESTIONS)]


def _question_parts(chunk: Sequence[tuple[str, Question]]) -> list[tuple[str, str, str | None]]:
    return [("question", q.prompt[:MAX_QUESTION_CHARS_IN_PROMPT], label) for label, q in chunk]


def suggest_types(questions: Sequence[Question], existing: Sequence[str], ask: Ask) -> TypesResult:
    """One type per question, at most `MAX_TYPES` for the bank; an existing name is reused with
    its own spelling."""
    reasons: list[Reason] = []
    known: dict[str, str] = {}
    for name in existing[:MAX_EXISTING_TYPES]:
        if clean := _single_line(name)[:MAX_TYPE_NAME_CHARS]:
            known.setdefault(clean.casefold(), clean)
    types: list[str] = []
    assignment: dict[int, str] = {}
    pending = False
    for chunk in _chunks(questions):
        by_label = dict(chunk)
        parts = [("existing_types", "\n".join(known.values()), None), *_question_parts(chunk)]
        prompt = _build("bank_types", LlmTypes, parts)
        try:
            parsed = _call(ask, prompt, LlmTypes, reasons, f"questions_{chunk[0][0]}")
        except QuotaExceededError:
            pending = True
            break
        if parsed is None:
            continue
        for item in parsed.types:
            name = known.get(_single_line(item.name).casefold()) or _single_line(item.name)
            if name not in types and len(types) >= MAX_TYPES:
                reasons.append(Reason("type_cap", f"{len(item.questions)}"))
                continue
            for label in item.questions:
                question = by_label.get(label)
                if question is None:
                    reasons.append(Reason("unknown_label"))
                elif question.ord in assignment:
                    reasons.append(Reason("duplicate_assignment"))
                else:
                    assignment[question.ord] = name
                    if name not in types:
                        types.append(name)
                        known.setdefault(name.casefold(), name)
    untyped = [q.ord for q in questions if q.ord not in assignment]
    if untyped and not pending:
        reasons.append(Reason("untyped", f"{len(untyped)}"))
    return TypesResult(assignment, types, untyped, reasons, _status(reasons, pending))


# ---- map_sections ----------------------------------------------------------------------------


def map_sections(
    questions: Sequence[Question], sections: Sequence[Section], ask: Ask
) -> SectionsResult:
    """Section ids per question. The model gets labels S1..Sn and answers in labels; ids stay
    here."""
    reasons: list[Reason] = []
    unique = list({s.id: s for s in reversed(sections)}.values())[::-1][:MAX_SECTIONS]
    if not unique:
        if questions:
            reasons.append(Reason("no_syllabus"))
        return SectionsResult({}, [q.ord for q in questions], reasons, _status(reasons, False))
    ids = {f"S{n}": s.id for n, s in enumerate(unique, start=1)}
    section_parts = [
        ("section", _single_line(s.title)[:MAX_SECTION_TITLE_CHARS], label)
        for (label, _), s in zip(ids.items(), unique, strict=True)
    ]
    mapping: dict[int, list[str]] = {}
    pending = False
    for chunk in _chunks(questions):
        by_label = dict(chunk)
        prompt = _build("bank_sections", LlmMappings, [*section_parts, *_question_parts(chunk)])
        try:
            parsed = _call(ask, prompt, LlmMappings, reasons, f"questions_{chunk[0][0]}")
        except QuotaExceededError:
            pending = True
            break
        if parsed is None:
            continue
        for item in parsed.mappings:
            question = by_label.get(item.question)
            if question is None:
                reasons.append(Reason("unknown_label"))
                continue
            if question.ord in mapping:
                reasons.append(Reason("duplicate_assignment"))
                continue
            picked: list[str] = []
            for label in item.sections:
                section_id = ids.get(label)
                if section_id is None:
                    reasons.append(Reason("invented_label"))
                elif section_id not in picked:
                    picked.append(section_id)
            if picked:
                mapping[question.ord] = picked[:MAX_SECTIONS_PER_QUESTION]
    unmapped = [q.ord for q in questions if q.ord not in mapping]
    return SectionsResult(mapping, unmapped, reasons, _status(reasons, pending))


__all__ = [
    "MAX_TYPES",
    "BankPrompt",
    "Question",
    "Reason",
    "Section",
    "SectionsResult",
    "SplitResult",
    "TypesResult",
    "map_sections",
    "split_bank",
    "suggest_types",
]
