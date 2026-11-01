"""Event contracts (T4.1, ADR-0006): the JSON Schemas in `contracts/events/` and their examples.

Read from the repository's `contracts/` folder, never imported from another service (ADR-0003).
core-api's own Pydantic models must accept exactly what the schemas accept, on every example.
"""

import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ValidationError
from referencing import Registry, Resource

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "events"
EXAMPLES = CONTRACTS / "examples"

# ARCHITECTURE §7.3: every event the two services exchange.
EVENTS_IN_ARCH = [
    "document.uploaded.v1",
    "document.indexed.v1",
    "document.failed.v1",
    "session.confirmed.v1",
    "session.progress.v1",
    "session.processed.v1",
    "session.failed.v1",
    "grade.requested.v1",
    "grade.completed.v1",
    "user.deleted.v1",
    "submission.created.v1",
    "submission.processed.v1",
    "submission.failed.v1",
    "unit.saved.v1",
]

# ADR-0013 and ADR-0006: an event carries identifiers and object keys, never what a person wrote,
# a secret or the material the AI works from.
CONTENT_FIELDS = {
    "answer_text",
    "note_text",
    "email",
    "password",
    "token",
    "text",
    "description_raw",
    "prompt",
    "reference_answer",
    "rubric",
    "quote_text",
    "missing",
    "title",
    "summary",
}
# Allowed on purpose (plan E10, ADR-0006 point 6): session.confirmed.v1 carries the subject's
# existing units (id, title, summary) so ai-service can merge duplicates without calling back.
# A unit title and summary are short, AI-written digests, not what the learner wrote.
ALLOWED_CONTENT = {
    ("session.confirmed.v1", "existing_units", "title"),
    ("session.confirmed.v1", "existing_units", "summary"),
}

JSON = dict[str, Any]


def load(path: Path) -> JSON:
    return cast(JSON, json.loads(path.read_text(encoding="utf-8")))


def schema_files() -> list[Path]:
    return sorted(CONTRACTS.glob("*.schema.json"))


class SchemaValidator(Protocol):
    """The part of jsonschema's validator the tests use, typed (its stubs leave it partial)."""

    def validate(self, instance: Any) -> None: ...
    def iter_errors(self, instance: Any) -> Iterator[Any]: ...
    def is_valid(self, instance: Any) -> bool: ...


def registry() -> Registry[Any]:
    resources: list[tuple[str, Resource[Any]]] = [
        (load(p)["$id"], Resource.from_contents(load(p))) for p in schema_files()
    ]
    empty: Registry[Any] = Registry()
    return empty.with_resources(resources)


def validator(event_type: str) -> SchemaValidator:
    schema = load(CONTRACTS / f"{event_type}.schema.json")
    return cast(
        SchemaValidator,
        Draft202012Validator(schema, registry=registry(), format_checker=FormatChecker()),
    )


def example_files() -> list[Path]:
    return sorted(EXAMPLES.glob("*.json"))


def schema_name(example: Path) -> str:
    """`session.confirmed.v1.invalid-x.json` → `session.confirmed.v1`."""
    return example.name.removesuffix(".json").split(".invalid-")[0]


def is_invalid(example: Path) -> bool:
    return ".invalid-" in example.name


VALID = [p for p in example_files() if not is_invalid(p)]
INVALID = [p for p in example_files() if is_invalid(p)]


def test_contracts_folder_is_found() -> None:
    # Red when: the path to contracts/ breaks, so every parametrized test below silently has
    # nothing to run.
    assert (CONTRACTS / "envelope.schema.json").is_file()
    assert len(VALID) >= len(EVENTS_IN_ARCH)
    assert len(INVALID) >= len(EVENTS_IN_ARCH)


def test_every_event_in_arch_has_schema_and_examples() -> None:
    # Red when: an event in ARCHITECTURE §7.3 has no schema, no valid example or no invalid
    # example, or a schema exists for an event the architecture does not name.
    names = {p.name.removesuffix(".schema.json") for p in schema_files()}
    assert names == {*EVENTS_IN_ARCH, "envelope"}
    for event in EVENTS_IN_ARCH:
        assert (EXAMPLES / f"{event}.json").is_file(), event
        assert any(schema_name(p) == event for p in INVALID), event
    for example in example_files():
        assert schema_name(example) in names, example.name


@pytest.mark.parametrize("path", schema_files(), ids=lambda p: p.name)
def test_schema_is_valid_draft_2020_12(path: Path) -> None:
    # Red when: a schema is malformed, so validation would test nothing.
    schema = load(path)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_envelope_lists_exactly_the_events_in_arch() -> None:
    # Red when: the envelope's event_type enum drifts from the schemas.
    envelope = load(CONTRACTS / "envelope.schema.json")
    assert sorted(envelope["properties"]["event_type"]["enum"]) == sorted(EVENTS_IN_ARCH)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_examples_pass(path: Path) -> None:
    # Red when: a schema rejects its own valid example.
    example = load(path)
    validator(schema_name(path)).validate(example)
    if schema_name(path) != "envelope":
        validator("envelope").validate(example)
        assert example["event_type"] == schema_name(path)


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_examples_rejected(path: Path) -> None:
    # Red when: a schema lets through a missing field, an extra field, a bad format or a value
    # out of range.
    errors = list(validator(schema_name(path)).iter_errors(load(path)))
    assert errors, f"{path.name} should be rejected"


@pytest.mark.parametrize("path", example_files(), ids=lambda p: p.name)
def test_pydantic_envelope_agrees_with_schema(path: Path) -> None:
    # Red when: core-api's models accept what the schema rejects, or reject what it accepts.
    from core_api.messaging.envelope import parse_event

    raw = path.read_text(encoding="utf-8")
    example = load(path)
    schema_accepts = validator("envelope").is_valid(example)
    event_type = example.get("event_type")
    if schema_accepts and isinstance(event_type, str):
        schema_accepts = validator(event_type).is_valid(example)
    try:
        parse_event(raw)
        pydantic_accepts = True
    except ValidationError:
        pydantic_accepts = False
    assert pydantic_accepts == schema_accepts
    assert pydantic_accepts == (not is_invalid(path))


def walk_properties(node: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[str, ...]]:
    """Every property name declared anywhere in a schema, with the property path to it."""
    if isinstance(node, dict):
        node = cast(JSON, node)
        for name, sub in cast(JSON, node.get("properties", {})).items():
            yield (*path, name)
            yield from walk_properties(sub, (*path, name))
        for key in ("items", "additionalProperties"):
            yield from walk_properties(node.get(key), path)
        for key in ("$defs", "patternProperties"):
            for sub in cast(JSON, node.get(key, {})).values():
                yield from walk_properties(sub, path)
        for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            for sub in cast(list[Any], node.get(key, [])):
                yield from walk_properties(sub, path)
        for key in ("if", "then", "else", "not"):
            yield from walk_properties(node.get(key), path)


def content_fields(schema: JSON, event: str) -> list[tuple[str, ...]]:
    return [
        (event, *path)
        for path in walk_properties(schema)
        if path[-1] in CONTENT_FIELDS and (event, *path[-2:]) not in ALLOWED_CONTENT
    ]


def test_no_schema_property_carries_content() -> None:
    # Red when: a schema gains a field that carries an answer, a note, a secret or AI material
    # (ADR-0013: what the learner wrote never leaves through an event).
    hits = [
        hit
        for path in schema_files()
        for hit in content_fields(load(path), path.name.removesuffix(".schema.json"))
    ]
    assert hits == []


def test_content_scan_catches_a_planted_field() -> None:
    # Red when: the scan stops descending into items, $defs or nested objects.
    nested: JSON = {
        "properties": {
            "payload": {
                "properties": {"list": {"items": {"$ref": "#/$defs/x"}}},
                "$defs": {"x": {"properties": {"answer_text": {"type": "string"}}}},
            },
            "deep": {"items": {"properties": {"note_text": {}}}},
        }
    }
    assert {hit[-1] for hit in content_fields(nested, "x")} == {"answer_text", "note_text"}
    allowed: JSON = {
        "properties": {"existing_units": {"items": {"properties": {"title": {}, "summary": {}}}}}
    }
    assert content_fields(allowed, "session.confirmed.v1") == []
    assert len(content_fields(allowed, "grade.completed.v1")) == 2


def object_schemas(node: Any, path: str = "#") -> Iterator[tuple[str, JSON]]:
    if isinstance(node, dict):
        node = cast(JSON, node)
        if node.get("type") == "object" or "properties" in node:
            yield path, node
        for key, sub in node.items():
            if isinstance(sub, dict):
                yield from object_schemas(sub, f"{path}/{key}")
            elif isinstance(sub, list):
                for i, item in enumerate(cast(list[Any], sub)):
                    yield from object_schemas(item, f"{path}/{key}/{i}")


@pytest.mark.parametrize("path", schema_files(), ids=lambda p: p.name)
def test_every_object_is_closed(path: Path) -> None:
    # Red when: an object in a schema accepts properties it does not declare, so a producer
    # could slip content into an event unnoticed.
    schema = load(path)
    open_objects = [
        where
        for where, node in object_schemas(schema)
        # The envelope leaves `payload` open: each event schema closes it.
        if node.get("additionalProperties") is not False
        and node.get("unevaluatedProperties") is not False
        and not (path.name == "envelope.schema.json" and where == "#/properties/payload")
    ]
    assert open_objects == []


# --- Events built in code (what a producer sends) ------------------------------------------

NOT_UTC = [
    datetime(2026, 10, 25, 8, 30),
    datetime(2026, 10, 25, 15, 30, tzinfo=timezone(timedelta(hours=7))),
]


def rebuilt(event: BaseModel, **changes: Any) -> BaseModel:
    """`event` validated again from Python values, as a producer builds one, with `changes`."""
    return type(event).model_validate({**event.model_dump(exclude_none=True), **changes})


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_dumped_event_matches_schema_and_parses_back(path: Path) -> None:
    # Red when: what core-api writes on the wire drifts from the contract (a null field, a
    # timestamp without Z), so ai-service would refuse core-api's own events.
    from core_api.messaging.envelope import dump_event, parse_event

    event = parse_event(path.read_text(encoding="utf-8"))
    wire = dump_event(event)
    validator(event.event_type).validate(json.loads(wire))
    assert parse_event(wire) == event


def test_empty_trace_context_dumps_valid() -> None:
    # Red when: an event produced outside any span writes `"traceparent": null`.
    from core_api.messaging.envelope import TraceContext, dump_event, parse_event

    event = parse_event((EXAMPLES / "user.deleted.v1.json").read_text(encoding="utf-8"))
    wire = dump_event(rebuilt(event, trace_context=TraceContext()))  # pyright: ignore[reportArgumentType]
    assert json.loads(wire)["trace_context"] == {}
    validator("user.deleted.v1").validate(json.loads(wire))
    assert parse_event(wire).trace_context == TraceContext()


def test_a_session_of_notes_only_has_no_ranges() -> None:
    # Red when: an empty `ranges` is refused or dropped on the way out (US-02 AC10).
    from core_api.messaging.envelope import dump_event, parse_event

    event = parse_event((EXAMPLES / "session.confirmed.v1.json").read_text(encoding="utf-8"))
    payload = event.payload.model_dump(exclude_none=True)
    notes_only: dict[str, Any] = {**payload, "ranges": []}
    wire = dump_event(rebuilt(event, payload=notes_only))  # pyright: ignore[reportArgumentType]
    assert json.loads(wire)["payload"]["ranges"] == []
    validator("session.confirmed.v1").validate(json.loads(wire))


@pytest.mark.parametrize("occurred_at", NOT_UTC, ids=["naive", "plus-07"])
def test_event_built_with_non_utc_time_is_refused(occurred_at: datetime) -> None:
    # Red when: a producer can build an event whose occurred_at is naive or not UTC; it would be
    # written without the Z the contract requires.
    from core_api.messaging.envelope import parse_event

    event = parse_event((EXAMPLES / "user.deleted.v1.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        rebuilt(event, occurred_at=occurred_at)
