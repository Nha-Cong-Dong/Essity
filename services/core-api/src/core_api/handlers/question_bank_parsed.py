"""Store what ai-service parsed out of a question bank (T8.1b, US-14 AC1-AC3, AC8).

Not an event handler: core calls ai-service over HTTP (as T7.9 and T9.6b do) and hands the reply
here, in the caller's transaction. The reply is untrusted (R03 layer 2): a section id core did
not send is dropped, text is stored as received but only after the strict contract, and nothing
here logs a question, answer or type name (ADR-0013).

- `source = bank`; `answer_origin = bank` exactly when the bank gave an answer, else both answer
  columns stay empty (AC1). Nothing here rewrites a stored question.
- A suggested type is reused by name or created with the default reference time (AC2).
- Sections link through `question_section`; a question left without one counts as unmapped and
  shows the "chưa gắn mục" line later (AC3).
- A question already stored (same `content_hash`, active) is skipped (AC8). The insert itself
  ignores the unique index, so two imports racing add each question once.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core_api.clients.bank_contract import BankReply
from core_api.db.models import Document, Question, QuestionSection, QuestionType
from core_api.domain.question_bank import (
    NewQuestion,
    default_ref_time_s,
    new_questions,
    reference_answer_of,
)

_log = logging.getLogger("core_api.handlers")

BANK_LEVEL = (
    1  # `question.level` is NOT NULL and being retired (T5.R): bank questions do not use it
)


@dataclass(frozen=True)
class Imported:
    added: int
    duplicates: int
    unmapped: int
    types_added: int


def _section_ids(item: NewQuestion, sent: set[uuid.UUID]) -> list[uuid.UUID]:
    picked: list[uuid.UUID] = []
    for raw in item.section_ids:
        try:
            section_id = uuid.UUID(raw)
        except ValueError:
            continue
        if section_id in sent and section_id not in picked:
            picked.append(section_id)
    return picked


def store_parsed(
    session: Session,
    user_id: uuid.UUID,
    document: Document,
    reply: BankReply,
    sent_sections: set[uuid.UUID],
) -> Imported:
    subject_id = document.subject_id
    known = set(
        session.scalars(
            select(Question.content_hash).where(
                Question.user_id == user_id,
                Question.subject_id == subject_id,
                Question.status == "active",
            )
        )
    )
    fresh, duplicates = new_questions(reply.questions, known)
    types = {
        t.name: t
        for t in session.scalars(
            select(QuestionType).where(
                QuestionType.user_id == user_id, QuestionType.subject_id == subject_id
            )
        )
    }
    types_added = 0
    added = unmapped = 0
    for item in fresh:
        kind = None
        if item.type_name is not None:
            kind = types.get(item.type_name)
            if kind is None:
                kind = QuestionType(
                    user_id=user_id,
                    subject_id=subject_id,
                    name=item.type_name,
                    ref_time_s=default_ref_time_s(),
                    ref_origin="default",
                )
                session.add(kind)
                session.flush()
                types[item.type_name] = kind
                types_added += 1
        question_id = uuid.uuid4()
        inserted = session.execute(
            insert(Question)
            .values(
                id=question_id,
                user_id=user_id,
                subject_id=subject_id,
                level=BANK_LEVEL,
                prompt=item.prompt,
                reference_answer=reference_answer_of(item.answer_text),
                status="active",
                content_hash=item.content_hash,
                run_id=reply.run_id,
                source="bank",
                type_id=None if kind is None else kind.id,
                quality_status="ok",
                answer_text=item.answer_text,
                answer_origin=None if item.answer_text is None else "bank",
                bank_document_id=document.id,
                bank_ord=item.ord - 1,
                # Not now(): the questions of one import keep the order of the bank.
                created_at=func.clock_timestamp(),
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "subject_id", "content_hash"],
                index_where=text("status = 'active'"),
            )
            .returning(Question.id)
        ).scalar_one_or_none()
        if inserted is None:
            duplicates += 1
            continue
        added += 1
        linked = _section_ids(item, sent_sections)
        if not linked:
            unmapped += 1
        for section_id in linked:
            session.add(
                QuestionSection(
                    user_id=user_id,
                    subject_id=subject_id,
                    question_id=question_id,
                    section_id=section_id,
                )
            )
    session.flush()
    _log.info(
        "question bank stored",
        extra={"outcome": "stored" if added else "none", "count": added},
    )
    return Imported(added, duplicates, unmapped, types_added)
