"""Text that reaches Postgres goes through `core_api.api.text` (plan D1, D10).

`storable_text` refuses what Postgres text cannot hold (NUL) or UTF-8 cannot encode (a lone
surrogate, which Pydantic keeps in a field without a length or pattern constraint), and every
other control character. The scan walks every route's parameters, as FastAPI builds them, so a
new request model with a bare `str` field turns it red.
"""

import types
import typing
from collections.abc import Callable, Iterator
from typing import Annotated, Any

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import AfterValidator, BaseModel, ValidationError
from starlette.routing import BaseRoute

from core_api.api import subjects, text
from core_api.api.text import DbText, Email, LoginEmail, storable_text
from core_api.main import app

# Checked by one of these, or exempt below.
CHECKS: set[Callable[..., Any]] = {text.storable_text, text.storable_email, subjects._name}  # pyright: ignore[reportPrivateUsage]
# Only hashed, never stored or sent to a query: any character is allowed (plan D4, D5).
EXEMPT = {"password", "token"}


# --- storable_text --------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["Mạng máy tính", "a b", "", "日本語 🙂", "ﬁ①"])
def test_ordinary_text_is_kept_as_is(value: str) -> None:
    assert storable_text(value) == value


@pytest.mark.parametrize("value", ["a\x00b", "a\tb", "a\nb", "a\x1fb", "a\x7fb", "a\x85b"])
def test_control_characters_are_refused(value: str) -> None:
    with pytest.raises(ValueError, match="control characters"):
        storable_text(value)


def test_a_lone_surrogate_is_refused() -> None:
    with pytest.raises(ValueError, match="valid Unicode"):
        storable_text("a\ud800b")


def test_format_characters_are_not_control_characters() -> None:
    """Zero-width joiners are Cf, not Cc: emoji sequences and some scripts need them."""
    assert storable_text("👩‍💻") == "👩‍💻"


class Probe(BaseModel):
    text: DbText
    email: Email
    login_email: LoginEmail


def probe(**fields: str) -> dict[str, str]:
    values = {"text": "x", "email": "a@example.com", "login_email": "a@example.com"} | fields
    return Probe.model_validate(values).model_dump()


def test_db_text_refuses_a_surrogate_without_any_length_constraint() -> None:
    with pytest.raises(ValidationError):
        probe(text="a\ud800b")


@pytest.mark.parametrize("field", ["email", "login_email"])
def test_emails_are_checked_after_the_strip_they_are_stored_with(field: str) -> None:
    """Reviewer plan #3: what passes is what `normalize_email` keeps."""
    assert probe(**{field: " a@example.com\x1f\n"})[field] == " a@example.com\x1f\n"
    with pytest.raises(ValidationError):
        probe(**{field: "a\x1f@example.com"})


def test_login_email_has_no_shape_rule() -> None:
    assert probe(login_email="not-an-email")["login_email"] == "not-an-email"
    with pytest.raises(ValidationError):
        probe(email="not-an-email")


# --- The scan -------------------------------------------------------------------------------------


def _checks_in(metadata: typing.Iterable[object]) -> set[Callable[..., Any]]:
    return {m.func for m in metadata if isinstance(m, AfterValidator)}


def _unchecked(tp: object, where: str, checks: set[Callable[..., Any]]) -> Iterator[str]:
    """Paths of `str` values under `tp` that no storable check guards."""
    origin = typing.get_origin(tp)
    if origin is Annotated:
        inner, *metadata = typing.get_args(tp)
        yield from _unchecked(inner, where, checks | _checks_in(metadata))
    elif tp is str:
        if not checks & CHECKS:
            yield where
    elif isinstance(tp, type) and issubclass(tp, BaseModel):
        for name, field in tp.model_fields.items():
            if name in EXEMPT:
                continue
            annotated = (
                Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation
            )
            yield from _unchecked(annotated, f"{where}.{name}", set())
    elif origin in (typing.Union, types.UnionType, list, tuple, set, frozenset, dict):
        for arg in typing.get_args(tp):
            yield from _unchecked(arg, where, checks)


def _params(dependant: Dependant) -> Iterator[tuple[str, object, list[object]]]:
    for kind in ("path_params", "query_params", "header_params", "cookie_params", "body_params"):
        for param in getattr(dependant, kind):
            yield param.name, param.field_info.annotation, list(param.field_info.metadata)
    for sub in dependant.dependencies:
        yield from _params(sub)


def unchecked_text(routes: list[BaseRoute]) -> list[str]:
    found: list[str] = []
    for context in iter_route_contexts(routes):
        if not isinstance(context.original_route, APIRoute):
            continue
        for name, annotation, metadata in _params(context.dependant):
            if name in EXEMPT:
                continue
            tp = Annotated[annotation, *metadata] if metadata else annotation
            found += [f"{context.path} {p}" for p in _unchecked(tp, name, set())]
    return found


def test_every_text_parameter_of_every_route_is_checked() -> None:
    assert unchecked_text(app.routes) == []


def test_the_scan_finds_a_bare_str() -> None:
    class Nested(BaseModel):
        note: str

    class Careless(BaseModel):
        title: str | None = None
        tags: list[str] = []
        nested: Nested | None = None
        name: DbText = ""
        password: str = ""

    probe_app = FastAPI()

    @probe_app.post("/careless/{slug}")
    def careless(slug: str, body: Careless, q: str = "") -> None: ...

    assert sorted(unchecked_text(probe_app.routes)) == [
        "/careless/{slug} body.nested.note",
        "/careless/{slug} body.tags",
        "/careless/{slug} body.title",
        "/careless/{slug} q",
        "/careless/{slug} slug",
    ]
