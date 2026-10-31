"""Every table model, imported here so Alembic autogenerate sees all of them."""

from core_api.db.models.auth_session import AuthSession
from core_api.db.models.command import CommandLog
from core_api.db.models.document import DocSection, Document
from core_api.db.models.email_token import EmailToken
from core_api.db.models.grade_job import GradeJob
from core_api.db.models.outbox import Outbox
from core_api.db.models.practice import PracticeLog, PracticeState
from core_api.db.models.processed_event import ProcessedEvent
from core_api.db.models.question import Question, QuestionSection, QuestionType, QuestionUnit
from core_api.db.models.review import (
    Attempt,
    Grade,
    GradeUnit,
    MemoryState,
    ReviewLog,
    ReviewSession,
    ReviewSessionItem,
)
from core_api.db.models.study_session import (
    NoteFile,
    NoteUpload,
    SessionRange,
    StudyLedger,
    StudySession,
    Submission,
)
from core_api.db.models.subject import Exam, Subject
from core_api.db.models.unit import (
    Anchor,
    KnowledgeUnit,
    UnitEdge,
    UnitLineage,
    UnitRevision,
    UnitSection,
)
from core_api.db.models.user import User

__all__ = [
    "Anchor",
    "Attempt",
    "AuthSession",
    "CommandLog",
    "DocSection",
    "Document",
    "EmailToken",
    "Exam",
    "Grade",
    "GradeJob",
    "GradeUnit",
    "KnowledgeUnit",
    "MemoryState",
    "NoteFile",
    "NoteUpload",
    "Outbox",
    "PracticeLog",
    "PracticeState",
    "ProcessedEvent",
    "Question",
    "QuestionSection",
    "QuestionType",
    "QuestionUnit",
    "ReviewLog",
    "ReviewSession",
    "ReviewSessionItem",
    "SessionRange",
    "StudyLedger",
    "StudySession",
    "Subject",
    "Submission",
    "UnitEdge",
    "UnitLineage",
    "UnitRevision",
    "UnitSection",
    "User",
]
