"""Every table model, imported here so Alembic autogenerate sees all of them."""

from core_api.db.models.auth_session import AuthSession
from core_api.db.models.email_token import EmailToken
from core_api.db.models.subject import Exam, Subject
from core_api.db.models.user import User

__all__ = ["AuthSession", "EmailToken", "Exam", "Subject", "User"]
