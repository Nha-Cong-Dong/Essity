"""Request text that reaches Postgres: what it can store and nothing a person never types.

Postgres text cannot hold NUL, and UTF-8 cannot encode a lone surrogate, which JSON can carry
as a "\\ud800" escape and Pydantic keeps in a field without a length or pattern constraint.
Other control characters have no place in a name or an address either. Every route parameter
that is text goes through one of these types; `tests/test_text_rule.py` scans for the rest.
Passwords and tokens are only hashed, so they are exempt and keep any character.
"""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator, Field

from core_api.domain.email import normalize_email

EMAIL_MAX = 320


def is_unicode(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def has_control(value: str) -> bool:
    return any(unicodedata.category(c) == "Cc" for c in value)


def storable_text(value: str) -> str:
    if not is_unicode(value):
        raise ValueError("must be valid Unicode text")
    if has_control(value):
        raise ValueError("cannot contain control characters")
    return value


def storable_email(value: str) -> str:
    # Checked as it will be stored: the surrounding whitespace a paste brings was always
    # stripped, and Python's strip also drops \x1c-\x1f and \x85 (reviewer plan #3).
    storable_text(normalize_email(value))
    return value


DbText = Annotated[str, AfterValidator(storable_text)]
# A light shape check; whether the address works is proven by the verification link.
Email = Annotated[
    str,
    Field(max_length=EMAIL_MAX, pattern=r"^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$"),
    AfterValidator(storable_email),
]
# No shape rule at login: a wrong-looking address answers like a wrong one (401).
LoginEmail = Annotated[str, Field(max_length=EMAIL_MAX), AfterValidator(storable_email)]
