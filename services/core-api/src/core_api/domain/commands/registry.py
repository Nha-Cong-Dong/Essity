"""Operation registry: each parse-command op kind maps to a typed pure operation (T9.2a).

Shapes mirror `ai_service.commands.schema` (T9.1, #78). A kind that is not registered cannot run
(AC6: no op deletes a canonical card, a subject, a document or a bank, resets FSRS, changes a cap
or an account). Every handler takes a snapshot and returns a new one; it raises `CommandRejected`
before changing anything it cannot finish.

Small choices the docs leave open (see .work/T9.2a/decisions.md): merge folds the texts into the
first card with a blank line between them and discards the others; split cuts at line breaks
into contiguous groups of near-equal size, the first group staying in the original card.
"""

import datetime
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from typing import Any

from core_api.domain.commands.state import (
    Card,
    CardStatus,
    Question,
    Section,
    Snapshot,
    StudyFilter,
)

JOIN = "\n\n"
type IdSource = Callable[[], uuid.UUID]


class CommandRejected(Exception):
    """A command that cannot run; `code` is machine-readable, `detail` names the culprit."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Op:
    pass


@dataclass(frozen=True)
class CardEdit(Op):
    card: uuid.UUID
    text: str


@dataclass(frozen=True)
class CardMerge(Op):
    cards: Sequence[uuid.UUID]


@dataclass(frozen=True)
class CardSplit(Op):
    card: uuid.UUID
    parts: int


@dataclass(frozen=True)
class CardAdd(Op):
    text: str
    section: uuid.UUID | None = None


@dataclass(frozen=True)
class CardDiscardDraft(Op):
    card: uuid.UUID


@dataclass(frozen=True)
class CardAddIdea(Op):
    card: uuid.UUID
    document: uuid.UUID
    text: str


@dataclass(frozen=True)
class SectionSetPages(Op):
    section: uuid.UUID
    from_page: int
    to_page: int


@dataclass(frozen=True)
class SectionExclude(Op):
    sections: Sequence[uuid.UUID]


@dataclass(frozen=True)
class SectionMark(Op):
    sections: Sequence[uuid.UUID]
    studied: bool


@dataclass(frozen=True)
class SuggestOnlySubject(Op):
    subject: uuid.UUID
    until: datetime.date


@dataclass(frozen=True)
class SuggestDeferSubject(Op):
    subject: uuid.UUID
    until: datetime.date


@dataclass(frozen=True)
class QuestionSetType(Op):
    question: uuid.UUID
    question_type: uuid.UUID


@dataclass(frozen=True)
class QuestionRelink(Op):
    question: uuid.UUID
    card: uuid.UUID | None = None
    section: uuid.UUID | None = None


@dataclass(frozen=True)
class QuestionSetAnswer(Op):
    question: uuid.UUID
    text: str


@dataclass(frozen=True)
class QuestionRemoveFromPractice(Op):
    question: uuid.UUID


# --- lookups ---------------------------------------------------------------------------------


def _own[T](state: Snapshot, kind: str, id_: uuid.UUID, cls: type[T]) -> T:
    """The record `id_` of this user, or a rejection (ids of other users look like missing)."""
    record = state.get(kind, id_)
    if record is None or record.user_id != state.user_id or not isinstance(record, cls):
        raise CommandRejected("not_owned", f"{kind} {id_}")
    return record


def _card(state: Snapshot, id_: uuid.UUID) -> Card:
    card = _own(state, "card", id_, Card)
    if card.status is CardStatus.DISCARDED:
        raise CommandRejected("card_discarded", str(id_))
    return card


def _draft(state: Snapshot, id_: uuid.UUID) -> Card:
    card = _card(state, id_)
    if card.status is not CardStatus.DRAFT:
        raise CommandRejected("canonical_card", str(id_))
    return card


def _section(state: Snapshot, id_: uuid.UUID) -> Section:
    return _own(state, "section", id_, Section)


def _question(state: Snapshot, id_: uuid.UUID) -> Question:
    return _own(state, "question", id_, Question)


def _exists(state: Snapshot, kind: str, id_: uuid.UUID) -> None:
    if (r := state.get(kind, id_)) is None or r.user_id != state.user_id:
        raise CommandRejected("not_owned", f"{kind} {id_}")


def _distinct(ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(ids)) != len(ids):
        raise CommandRejected("duplicate_target")
    return list(ids)


# --- handlers --------------------------------------------------------------------------------


def split_text(text: str, parts: int) -> list[str]:
    """Deterministic split points: contiguous groups of non-empty lines, sizes differ by <= 1."""
    lines = [line for line in text.splitlines() if line.strip()]
    if parts < 2 or len(lines) < parts:
        raise CommandRejected("too_short_to_split", f"{len(lines)} lines for {parts} parts")
    size, extra = divmod(len(lines), parts)
    out, start = [], 0
    for i in range(parts):
        end = start + size + (1 if i < extra else 0)
        out.append("\n".join(lines[start:end]))
        start = end
    return out


def _card_edit(s: Snapshot, op: CardEdit, ids: IdSource) -> Snapshot:
    return s.put(_card(s, op.card).changed(text=op.text))


def _card_merge(s: Snapshot, op: CardMerge, ids: IdSource) -> Snapshot:
    targets = _distinct(op.cards)
    if len(targets) < 2:
        raise CommandRejected("merge_needs_two")
    cards = [_draft(s, c) for c in targets]
    out = s.put(cards[0].changed(text=JOIN.join(c.text for c in cards)))
    for card in cards[1:]:
        out = out.put(card.changed(status=CardStatus.DISCARDED))
    return out


def _card_split(s: Snapshot, op: CardSplit, ids: IdSource) -> Snapshot:
    card = _draft(s, op.card)
    texts = split_text(card.text, op.parts)
    out = s.put(card.changed(text=texts[0]))
    for text in texts[1:]:
        out = out.put(
            Card(ids(), s.user_id, text=text, status=CardStatus.DRAFT, section_id=card.section_id)
        )
    return out


def _card_add(s: Snapshot, op: CardAdd, ids: IdSource) -> Snapshot:
    if op.section is not None:
        _section(s, op.section)
    return s.put(
        Card(ids(), s.user_id, text=op.text, status=CardStatus.DRAFT, section_id=op.section)
    )


def _card_discard(s: Snapshot, op: CardDiscardDraft, ids: IdSource) -> Snapshot:
    return s.put(_draft(s, op.card).changed(status=CardStatus.DISCARDED))


def _card_add_idea(s: Snapshot, op: CardAddIdea, ids: IdSource) -> Snapshot:
    card = _card(s, op.card)
    _exists(s, "document", op.document)
    return s.put(card.changed(text=f"{card.text}\n{op.text}" if card.text else op.text))


def _section_set_pages(s: Snapshot, op: SectionSetPages, ids: IdSource) -> Snapshot:
    if op.from_page < 1 or op.to_page < op.from_page:
        raise CommandRejected("bad_pages", f"{op.from_page}-{op.to_page}")
    return s.put(_section(s, op.section).changed(from_page=op.from_page, to_page=op.to_page))


def _section_exclude(s: Snapshot, op: SectionExclude, ids: IdSource) -> Snapshot:
    for target in _distinct(op.sections):
        s = s.put(_section(s, target).changed(excluded=True))
    return s


def _section_mark(s: Snapshot, op: SectionMark, ids: IdSource) -> Snapshot:
    for target in _distinct(op.sections):
        s = s.put(_section(s, target).changed(studied=op.studied))
    return s


def _filter(mode: str) -> Callable[[Snapshot, Any, IdSource], Snapshot]:
    def run(s: Snapshot, op: SuggestOnlySubject | SuggestDeferSubject, ids: IdSource) -> Snapshot:
        _exists(s, "subject", op.subject)
        existing = s.get("filter", op.subject)
        if isinstance(existing, StudyFilter):
            return s.put(existing.changed(mode=mode, until=op.until))
        return s.put(StudyFilter(op.subject, s.user_id, mode=mode, until=op.until))

    return run


def _question_set_type(s: Snapshot, op: QuestionSetType, ids: IdSource) -> Snapshot:
    question = _question(s, op.question)
    _exists(s, "question_type", op.question_type)
    return s.put(question.changed(question_type_id=op.question_type))


def _question_relink(s: Snapshot, op: QuestionRelink, ids: IdSource) -> Snapshot:
    if (op.card is None) == (op.section is None):
        raise CommandRejected("exactly_one_target")
    question = _question(s, op.question)
    if op.card is not None:
        _card(s, op.card)
    elif op.section is not None:
        _section(s, op.section)
    return s.put(question.changed(card_id=op.card, section_id=op.section))


def _question_set_answer(s: Snapshot, op: QuestionSetAnswer, ids: IdSource) -> Snapshot:
    return s.put(_question(s, op.question).changed(answer=op.text))


def _question_remove(s: Snapshot, op: QuestionRemoveFromPractice, ids: IdSource) -> Snapshot:
    return s.put(_question(s, op.question).changed(in_practice=False))


@dataclass(frozen=True)
class Entry:
    op: type[Op]
    run: Callable[[Snapshot, Any, IdSource], Snapshot]


REGISTRY: dict[str, Entry] = {
    "card_edit": Entry(CardEdit, _card_edit),
    "card_merge": Entry(CardMerge, _card_merge),
    "card_split": Entry(CardSplit, _card_split),
    "card_add": Entry(CardAdd, _card_add),
    "card_discard_draft": Entry(CardDiscardDraft, _card_discard),
    "card_add_idea": Entry(CardAddIdea, _card_add_idea),
    "section_set_pages": Entry(SectionSetPages, _section_set_pages),
    "section_exclude": Entry(SectionExclude, _section_exclude),
    "section_mark": Entry(SectionMark, _section_mark),
    "suggest_only_subject": Entry(SuggestOnlySubject, _filter("only")),
    "suggest_defer_subject": Entry(SuggestDeferSubject, _filter("defer")),
    "question_set_type": Entry(QuestionSetType, _question_set_type),
    "question_relink": Entry(QuestionRelink, _question_relink),
    "question_set_answer": Entry(QuestionSetAnswer, _question_set_answer),
    "question_remove_from_practice": Entry(QuestionRemoveFromPractice, _question_remove),
}
_KIND_OF = {entry.op: kind for kind, entry in REGISTRY.items()}


def kind_of(op: Op) -> str:
    return _KIND_OF[type(op)]


def run_op(state: Snapshot, op: Op, ids: IdSource) -> Snapshot:
    entry = REGISTRY.get(_KIND_OF.get(type(op), ""))
    if entry is None:
        raise CommandRejected("unsupported", type(op).__name__)
    return entry.run(state, op, ids)


_ID_FIELDS = ("card", "section", "document", "subject", "question", "question_type")


def op_from_json(data: dict[str, Any]) -> Op:
    """Build an op from a parse-command result; an unknown kind (incl. `unclear`) is refused."""
    kind = data.get("kind")
    entry = REGISTRY.get(kind) if isinstance(kind, str) else None
    if entry is None:
        raise CommandRejected("unsupported", str(kind))
    names = {f.name for f in fields(entry.op)}
    extra = set(data) - {"kind"} - names
    if extra:
        raise CommandRejected("unknown_fields", ",".join(sorted(extra)))
    values: dict[str, Any] = {}
    try:
        for name in names & set(data):
            v = data[name]
            if name in _ID_FIELDS:
                v = None if v is None else uuid.UUID(str(v))
            elif name in ("cards", "sections"):
                v = [uuid.UUID(str(x)) for x in v]
            elif name == "until":
                v = datetime.date.fromisoformat(str(v))
            values[name] = v
        return entry.op(**values)
    except (ValueError, TypeError) as exc:
        raise CommandRejected("invalid_op", str(kind)) from exc
