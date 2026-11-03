"""Usernames (US-12 D2): 3-20 characters of `a-z 0-9 _ .`, starting with a letter, not all
digits, no `..`, not a reserved word. Stored lowercase; compared after `normalize_username`.

`username_from_email` makes a legal, free name from an address: for the migration that gave
existing accounts a name (0035) and for accounts made without one (Google, T5.10).
"""

import re
from collections.abc import Container
from enum import StrEnum

MIN_LENGTH = 3
MAX_LENGTH = 20

_SHAPE = re.compile(r"[a-z][a-z0-9_.]{2,19}")
_FOREIGN = re.compile(r"[^a-z0-9_.]")
_DOTS = re.compile(r"\.{2,}")

# Names that could pass for the service or its staff. Not exhaustive: a list to grow.
RESERVED = frozenset(
    {
        "admin",
        "administrator",
        "root",
        "support",
        "essity",
        "api",
        "me",
        "help",
        "staff",
        "system",
        "moderator",
        "owner",
        "security",
        "postmaster",
        "noreply",
        "null",
        "undefined",
    }
)


class UsernameProblem(StrEnum):
    INVALID = "username_invalid"
    RESERVED = "username_reserved"


class UsernameRejectedError(ValueError):
    def __init__(self, problem: UsernameProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_username(username: str) -> str:
    """The name itself when it is legal (already normalized); raise `UsernameRejectedError`."""
    if (
        not _SHAPE.fullmatch(username)
        or ".." in username
        or username.isdigit()  # cannot happen after the first-letter rule; kept as the D2 text
    ):
        raise UsernameRejectedError(UsernameProblem.INVALID)
    if username in RESERVED:
        raise UsernameRejectedError(UsernameProblem.RESERVED)
    return username


def username_from_email(email: str, taken: Container[str]) -> str:
    """A legal username not in `taken`, from the part of `email` before the last `@`."""
    local = email.strip().lower().rpartition("@")[0]
    base = _FOREIGN.sub("", local).lstrip("0123456789_.")
    base = _DOTS.sub(".", base)[:MAX_LENGTH] or "user"
    base = base.ljust(MIN_LENGTH, "_")
    if base not in RESERVED and base not in taken:
        return base
    counter = 2
    while True:
        suffix = f"_{counter}"
        candidate = base[: MAX_LENGTH - len(suffix)] + suffix
        if candidate not in RESERVED and candidate not in taken:
            return candidate
        counter += 1
