"""The snapshot a command runs against: a user's records, immutable, keyed by (kind, id).

The core loads the snapshot (T9.2 service), these modules change it functionally. A record has
`rev`; every change bumps it, so history is append-only (US-18 AC5).
"""

import datetime
import uuid
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, ClassVar, Self


class CardStatus(StrEnum):
    DRAFT = "draft"
    CANONICAL = "canonical"
    DISCARDED = "discarded"


@dataclass(frozen=True)
class Record:
    KIND: ClassVar[str]
    id: uuid.UUID
    user_id: uuid.UUID
    rev: int = 1

    def changed(self, **fields: Any) -> Self:
        """The record with `fields` set and `rev` bumped, or itself when nothing differs."""
        if all(getattr(self, name) == value for name, value in fields.items()):
            return self
        return replace(self, rev=self.rev + 1, **fields)


@dataclass(frozen=True)
class Card(Record):
    KIND: ClassVar[str] = "card"
    text: str = ""
    status: CardStatus = CardStatus.DRAFT
    section_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Section(Record):
    KIND: ClassVar[str] = "section"
    from_page: int = 1
    to_page: int = 1
    excluded: bool = False
    studied: bool = False


@dataclass(frozen=True)
class Question(Record):
    KIND: ClassVar[str] = "question"
    question_type_id: uuid.UUID | None = None
    card_id: uuid.UUID | None = None
    section_id: uuid.UUID | None = None
    answer: str = ""
    in_practice: bool = True


@dataclass(frozen=True)
class StudyFilter(Record):
    """A suggestion filter; `id` is the subject it names (one filter per subject)."""

    KIND: ClassVar[str] = "filter"
    mode: str = "only"  # "only" | "defer"
    until: datetime.date = datetime.date.min


@dataclass(frozen=True)
class Subject(Record):
    """An id the user owns that commands only point at (never changed by a command)."""

    KIND: ClassVar[str] = "subject"


@dataclass(frozen=True)
class QuestionType(Record):
    KIND: ClassVar[str] = "question_type"


@dataclass(frozen=True)
class Document(Record):
    KIND: ClassVar[str] = "document"


type Key = tuple[str, uuid.UUID]


def key_of(record: Record) -> Key:
    return (record.KIND, record.id)


@dataclass(frozen=True)
class Snapshot:
    user_id: uuid.UUID
    records: dict[Key, Record]

    @classmethod
    def of(cls, user_id: uuid.UUID, records: list[Record]) -> "Snapshot":
        return cls(user_id, {key_of(r): r for r in records})

    def get(self, kind: str, id_: uuid.UUID) -> Record | None:
        return self.records.get((kind, id_))

    def put(self, record: Record) -> "Snapshot":
        return Snapshot(self.user_id, {**self.records, key_of(record): record})

    def drop(self, key: Key) -> "Snapshot":
        return Snapshot(self.user_id, {k: v for k, v in self.records.items() if k != key})
