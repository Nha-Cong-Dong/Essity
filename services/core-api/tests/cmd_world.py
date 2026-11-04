"""A user with a subject, an outline (a parent over two leaves), draft cards in a draft study
session, questions and a question type; a parser double that counts its calls."""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from core_api.db.models import (
    DocSection,
    Document,
    KnowledgeUnit,
    Question,
    QuestionType,
    StudySession,
    Subject,
    User,
)
from core_api.services.commands import ApplyOutcome, CommandRequest, CommandService
from v2_rows import (
    make_document,
    make_question,
    make_section,
    make_study_session,
    make_subject,
    make_type,
    make_unit,
)

SESSION = uuid.UUID(int=1)


class Parser:
    def __init__(self, ops: Sequence[Mapping[str, Any]] = ()) -> None:
        self.ops, self.calls = list(ops), 0

    def __call__(self, raw_text: str) -> Sequence[Mapping[str, Any]]:
        self.calls += 1
        return self.ops


class CmdWorld:
    def __init__(self, db: Session, user: User) -> None:
        self.db, self.user = db, user
        self.subject: Subject = make_subject(db, user)
        self.document: Document = make_document(db, user, self.subject, role="textbook")
        self.parent: DocSection = make_section(
            db, user, self.document, ord=0, title="Ch 1", weight=0
        )
        self.leaf1 = make_section(
            db, user, self.document, ord=0, title="1.1", parent_id=self.parent.id, weight=2
        )
        self.leaf2 = make_section(
            db, user, self.document, ord=1, title="1.2", parent_id=self.parent.id, weight=2
        )
        self.study: StudySession = make_study_session(db, user, self.subject)
        self.cards: list[KnowledgeUnit] = [
            make_unit(
                db,
                user,
                self.subject,
                title=f"Thẻ {i}",
                summary=f"Nội dung {i}\ndòng hai {i}",
                status="draft",
                session_id=self.study.id,
                section_id=self.leaf1.id,
            )
            for i in range(3)
        ]
        self.questions: list[Question] = [
            make_question(db, user, self.subject, n=i) for i in range(3)
        ]
        self.qtype: QuestionType = make_type(db, user, self.subject)
        self.service = CommandService(db, user.id)

    def run(
        self,
        ops: Sequence[Mapping[str, Any]],
        *,
        command_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        text: str = "lệnh",
    ) -> ApplyOutcome:
        return self.service.apply(
            command_id or uuid.uuid4(),
            session_id or SESSION,
            CommandRequest(text, None),
            parse=Parser(ops),
        )
