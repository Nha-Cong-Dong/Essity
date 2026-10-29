"""Rows of the v2 schema group 1 (T7.1), built the way the later tasks will: real parents, real
owners, one subject for Alice."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from clock import future_exam
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
from core_api.domain.documents import raw_key
from core_api.repositories.subject import SubjectRepository

RUN = uuid.uuid4()
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def make_subject(session: Session, user: User, name: str = "Mạng máy tính") -> Subject:
    subject, _ = SubjectRepository(session, user.id).create_with_exam(name, future_exam(60))
    session.flush()
    return subject


def make_document(
    session: Session, user: User, subject: Subject, sha: str = "ab" * 32, **overrides: Any
) -> Document:
    values: dict[str, Any] = {
        "user_id": user.id,
        "subject_id": subject.id,
        "short_name": "Giáo trình",
        "sha256": sha,
        "size_bytes": 10,
        "status": "pending",
        "presigned_at": NOW,
        "object_key": raw_key(user.id, subject.id, sha),
    }
    values.update(overrides)
    document = Document(**values)
    session.add(document)
    session.flush()
    return document


def make_section(session: Session, user: User, document: Document, **overrides: Any) -> DocSection:
    values: dict[str, Any] = {
        "user_id": user.id,
        "subject_id": document.subject_id,
        "document_id": document.id,
        "ord": 0,
        "title": "Chương 1",
        "unit": "page",
        "source": "bookmark",
    }
    values.update(overrides)
    section = DocSection(**values)
    session.add(section)
    session.flush()
    return section


def make_unit(session: Session, user: User, subject: Subject, **overrides: Any) -> KnowledgeUnit:
    values: dict[str, Any] = {
        "user_id": user.id,
        "subject_id": subject.id,
        "title": "Thẻ",
        "summary": "s",
        "kind": "concept",
        "run_id": RUN,
    }
    values.update(overrides)
    unit = KnowledgeUnit(**values)
    session.add(unit)
    session.flush()
    return unit


def make_question(
    session: Session, user: User, subject: Subject, n: int = 0, **overrides: Any
) -> Question:
    values: dict[str, Any] = {
        "user_id": user.id,
        "subject_id": subject.id,
        "level": 1,
        "prompt": f"Câu {n}?",
        "reference_answer": "Đáp án",
        "content_hash": f"{n:064x}",
        "run_id": RUN,
    }
    values.update(overrides)
    question = Question(**values)
    session.add(question)
    session.flush()
    return question


def make_type(session: Session, user: User, subject: Subject, **overrides: Any) -> QuestionType:
    values: dict[str, Any] = {
        "user_id": user.id,
        "subject_id": subject.id,
        "name": "Giải thích",
        "ref_time_s": 120,
        "ref_origin": "rubric",
    }
    values.update(overrides)
    question_type = QuestionType(**values)
    session.add(question_type)
    session.flush()
    return question_type


def make_study_session(session: Session, user: User, subject: Subject) -> StudySession:
    study = StudySession(
        user_id=user.id, subject_id=subject.id, description_raw="x", extraction="proposed"
    )
    session.add(study)
    session.flush()
    return study


@dataclass
class World:
    session: Session
    alice: User
    bob: User
    subject: Subject
    other_subject: Subject
