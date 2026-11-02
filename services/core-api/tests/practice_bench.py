"""Ready practice questions through the real tables (T8.5): a subject with a studied section that
has a canonical card, bank questions linked to it, and practice states."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from core_api.db.models import (
    DocSection,
    KnowledgeUnit,
    Question,
    QuestionSection,
    UnitSection,
    User,
)
from core_api.db.models import PracticeState as PracticeStateRow
from v2_rows import NOW, make_document, make_question, make_section, make_subject, make_unit

RUN = uuid.uuid4()


class Bench:
    """One user's subject with a textbook and a question bank document."""

    def __init__(self, session: Session, user: User, subject: Any = None) -> None:
        self.session, self.user = session, user
        self.subject = subject or make_subject(session, user)
        fields: dict[str, Any] = {
            "status": "indexed",
            "uploaded_at": NOW,
            "run_id": RUN,
            "page_count": 1,
            "toc_key": "d/toc.json",
            "page_labels_key": "d/labels.json",
            "page_text_key": "users/x/derived/p/pages.json",
            "thumbnails_prefix": "d/thumbs",
        }
        self.book = make_document(
            session, user, self.subject, sha=uuid.uuid4().hex * 2, role="textbook", **fields
        )
        self.bank = make_document(
            session, user, self.subject, sha=uuid.uuid4().hex * 2, role="question_bank", **fields
        )
        self.n = 0
        self.sections = 0
        self._ready: DocSection | None = None

    def section(self, title: str, studied: bool = True, **kw: Any) -> DocSection:
        weight = kw.pop("weight", 2.0)
        kw.setdefault("ord", self.sections)
        self.sections += 1
        return make_section(
            self.session,
            self.user,
            self.book,
            title=title,
            weight=weight,
            studied_weight=weight if studied else 0.0,
            **kw,
        )

    def card(self, section: DocSection, status: str = "canonical") -> KnowledgeUnit:
        unit = make_unit(self.session, self.user, self.subject, status=status)
        self.session.add(
            UnitSection(
                user_id=self.user.id,
                subject_id=self.subject.id,
                unit_id=unit.id,
                section_id=section.id,
            )
        )
        self.session.flush()
        return unit

    def question(self, *sections: DocSection, **kw: Any) -> Question:
        self.n += 1
        kw.setdefault("source", "bank")
        if kw["source"] == "bank":
            kw.setdefault("bank_document_id", self.bank.id)
            kw.setdefault("bank_ord", self.n)
            kw.setdefault("run_id", None)
        q = make_question(self.session, self.user, self.subject, self.n + 5000, **kw)
        for s in sections:
            self.session.add(
                QuestionSection(
                    user_id=self.user.id,
                    subject_id=self.subject.id,
                    question_id=q.id,
                    section_id=s.id,
                )
            )
        self.session.flush()
        return q

    def ready(self, **kw: Any) -> Question:
        """A ready bank question: its section is studied and has a canonical card."""
        if self._ready is None:
            self._ready = self.section("TCP")
            self.card(self._ready)
        return self.question(self._ready, **kw)


def schedule(
    session: Session,
    user: User,
    question: Question,
    due: datetime,
    *,
    removed: datetime | None = None,
    last_review: datetime | None = None,
) -> PracticeStateRow:
    """A practice state (review phase) due at `due`."""
    row = PracticeStateRow(
        user_id=user.id,
        question_id=question.id,
        phase="review",
        step=None,
        stability=10.0,
        difficulty=5.0,
        due=due,
        last_review=last_review or due - timedelta(days=10),
        removed_at=removed,
    )
    session.add(row)
    session.flush()
    return row
