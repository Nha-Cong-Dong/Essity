"""Structural rules that keep one user's data away from another (T1.3, ARCH §6.2)."""

import importlib
import inspect
import pkgutil

import core_api.repositories
from core_api.db.base import Base
from core_api.repositories.auth_session import AuthSessionRepository
from core_api.repositories.base import UserScopedRepository
from core_api.repositories.email_token import EmailTokenRepository
from core_api.repositories.user import UserRepository

# Repositories allowed to query without a user_id, and why.
UNSCOPED = {
    UserRepository: "finds the user in the first place (sign-up, login)",
    EmailTokenRepository: "finds the user from the token in an email link (nobody is signed in)",
    AuthSessionRepository: "finds the user from the session token of the request",
}


def repository_classes() -> set[type]:
    found: set[type] = set()
    for module_info in pkgutil.iter_modules(core_api.repositories.__path__):
        module = importlib.import_module(f"core_api.repositories.{module_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module.__name__ and obj.__name__.endswith("Repository"):
                found.add(obj)
    return found


def test_every_repository_is_scoped_to_a_user() -> None:
    unscoped = {
        cls.__name__
        for cls in repository_classes() - {UserScopedRepository}
        if not issubclass(cls, UserScopedRepository) and cls not in UNSCOPED
    }
    assert unscoped == set(), "repositories that can read data without a user_id"


def test_every_user_id_column_references_the_user_table() -> None:
    missing = {
        table.name
        for table in Base.metadata.tables.values()
        if "user_id" in table.c
        and not any(fk.column.table.name == "user" for fk in table.c.user_id.foreign_keys)
    }
    assert missing == set()


def test_the_rule_actually_finds_repositories() -> None:
    names = {cls.__name__ for cls in repository_classes()}
    assert {"UserRepository", "SubjectRepository", "ExamRepository", "BaselineRepository"} <= names
