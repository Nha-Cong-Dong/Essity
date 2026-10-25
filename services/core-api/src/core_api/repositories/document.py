"""Documents of a user (T4.5): every query scoped to them (ARCH §6.2)."""

from core_api.db.models import Document
from core_api.repositories.base import UserScopedRepository


class DocumentRepository(UserScopedRepository[Document]):
    model = Document
