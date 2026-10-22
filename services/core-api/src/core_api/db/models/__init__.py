"""Every table model, imported here so Alembic autogenerate sees all of them."""

from core_api.db.models.auth_session import AuthSession
from core_api.db.models.baseline import Baseline
from core_api.db.models.email_token import EmailToken
from core_api.db.models.question import Question, QuestionUnit
from core_api.db.models.subject import Exam, Subject
from core_api.db.models.unit import Anchor, KnowledgeUnit
from core_api.db.models.user import User

__all__ = [
    "Anchor",
    "AuthSession",
    "Baseline",
    "EmailToken",
    "Exam",
    "KnowledgeUnit",
    "Question",
    "QuestionUnit",
    "Subject",
    "User",
]
