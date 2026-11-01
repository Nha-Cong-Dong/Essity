"""Event contracts (T4.1, ADR-0006), checked from ai-service's side.

Reads `contracts/events/` from the repository, never imports core-api (ADR-0003). ai-service's own
Pydantic models must accept exactly what the JSON Schemas accept, on every example, and what they
write must pass the schemas.
"""

import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, cast, get_args

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ValidationError
from referencing import Registry, Resource

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "events"
EXAMPLES = CONTRACTS / "examples"
JSON = dict[str, Any]


class SchemaValidator(Protocol):
    """The part of jsonschema's validator the tests use, typed (its stubs leave it partial)."""

    def validate(self, instance: Any) -> None: ...
    def iter_errors(self, instance: Any) -> Iterator[Any]: ...
    def is_valid(self, instance: Any) -> bool: ...


def load(path: Path) -> JSON:
    return cast(JSON, json.loads(path.read_text(encoding="utf-8")))


def validator(name: str) -> SchemaValidator:
    """Validator for `<name>.schema.json`, resolving `$ref`s to the other contract files."""
    resources: list[tuple[str, Resource[Any]]] = [
        (load(p)["$id"], Resource.from_contents(load(p)))
        for p in sorted(CONTRACTS.glob("*.schema.json"))
    ]
    empty: Registry[Any] = Registry()
    schema = load(CONTRACTS / f"{name}.schema.json")
    return cast(
        SchemaValidator,
        Draft202012Validator(
            schema, registry=empty.with_resources(resources), format_checker=FormatChecker()
        ),
    )


# ARCHITECTURE §7.3.
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


def example_files() -> list[Path]:
    return sorted(EXAMPLES.glob("*.json"))


def schema_name(example: Path) -> str:
    """`session.confirmed.v1.invalid-x.json` → `session.confirmed.v1`."""
    return example.name.removesuffix(".json").split(".invalid-")[0]


VALID = [p for p in example_files() if ".invalid-" not in p.name]
INVALID = [p for p in example_files() if ".invalid-" in p.name]


def test_contracts_folder_is_found() -> None:
    # Red when: the path to contracts/ breaks, so the parametrized tests have nothing to run.
    assert (CONTRACTS / "envelope.schema.json").is_file()
    assert len(VALID) >= len(EVENTS_IN_ARCH)
    assert len(INVALID) >= len(EVENTS_IN_ARCH)


def test_every_event_in_arch_has_schema_and_examples() -> None:
    # Red when: an event in ARCHITECTURE §7.3 lacks a schema, a valid or an invalid example.
    for event in EVENTS_IN_ARCH:
        assert (CONTRACTS / f"{event}.schema.json").is_file(), event
        assert (EXAMPLES / f"{event}.json").is_file(), event
        assert any(schema_name(p) == event for p in INVALID), event


def test_models_cover_exactly_the_envelope_events() -> None:
    # Red when: ai-service has no model for an event the envelope lists, or one it does not.
    from ai_service.messaging.envelope import Event

    union = get_args(Event)[0]
    modelled = {get_args(m.model_fields["event_type"].annotation)[0] for m in get_args(union)}
    envelope = load(CONTRACTS / "envelope.schema.json")
    assert modelled == set(envelope["properties"]["event_type"]["enum"]) == set(EVENTS_IN_ARCH)


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_examples_pass(path: Path) -> None:
    # Red when: ai-service's models refuse an event the contract allows.
    from ai_service.messaging.envelope import parse_event

    event = parse_event(path.read_text(encoding="utf-8"))
    assert event.event_type == schema_name(path)


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_examples_rejected(path: Path) -> None:
    # Red when: ai-service's models take a missing field, an extra field, a bad format or a value
    # out of range that the contract refuses.
    from ai_service.messaging.envelope import parse_event

    with pytest.raises(ValidationError):
        parse_event(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_schema_rejects_invalid_examples(path: Path) -> None:
    # Red when: the schema itself lets through what its invalid example shows, so the model
    # check above would be the only guard.
    assert list(validator(schema_name(path)).iter_errors(load(path)))


@pytest.mark.parametrize("path", example_files(), ids=lambda p: p.name)
def test_pydantic_envelope_agrees_with_schema(path: Path) -> None:
    # Red when: ai-service's models accept what the schema rejects, or reject what it accepts.
    from ai_service.messaging.envelope import parse_event

    example = load(path)
    schema_accepts = validator("envelope").is_valid(example)
    event_type = example.get("event_type")
    if schema_accepts and isinstance(event_type, str):
        schema_accepts = validator(event_type).is_valid(example)
    try:
        parse_event(path.read_text(encoding="utf-8"))
        pydantic_accepts = True
    except ValidationError:
        pydantic_accepts = False
    assert pydantic_accepts == schema_accepts


# --- Events built in code (what ai-service will send) --------------------------------------

NOT_UTC = [
    datetime(2026, 10, 25, 8, 30),
    datetime(2026, 10, 25, 15, 30, tzinfo=timezone(timedelta(hours=7))),
]


def rebuilt(event: BaseModel, **changes: Any) -> BaseModel:
    """`event` validated again from Python values, as a producer builds one, with `changes`."""
    return type(event).model_validate({**event.model_dump(exclude_none=True), **changes})


def example(name: str) -> str:
    return (EXAMPLES / f"{name}.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_dumped_event_matches_schema_and_parses_back(path: Path) -> None:
    # Red when: what ai-service writes on the wire drifts from the contract (a null field, a
    # timestamp without Z), so core-api would refuse ai-service's events.
    from ai_service.messaging.envelope import dump_event, parse_event

    event = parse_event(path.read_text(encoding="utf-8"))
    wire = dump_event(event)
    validator(event.event_type).validate(json.loads(wire))
    assert parse_event(wire) == event


def test_empty_trace_context_dumps_valid() -> None:
    # Red when: an event produced outside any span writes `"traceparent": null`.
    from ai_service.messaging.envelope import TraceContext, dump_event, parse_event

    event = parse_event(example("user.deleted.v1"))
    wire = dump_event(rebuilt(event, trace_context=TraceContext()))  # pyright: ignore[reportArgumentType]
    assert json.loads(wire)["trace_context"] == {}
    validator("user.deleted.v1").validate(json.loads(wire))
    assert parse_event(wire).trace_context == TraceContext()


def test_a_session_of_notes_only_has_no_ranges() -> None:
    # Red when: an empty `ranges` is refused or dropped on the way out (US-02 AC10).
    from ai_service.messaging.envelope import dump_event, parse_event

    event = parse_event(example("session.confirmed.v1"))
    payload = event.payload.model_dump(exclude_none=True)
    notes_only: dict[str, Any] = {**payload, "ranges": []}
    wire = dump_event(rebuilt(event, payload=notes_only))  # pyright: ignore[reportArgumentType]
    assert json.loads(wire)["payload"]["ranges"] == []
    validator("session.confirmed.v1").validate(json.loads(wire))


@pytest.mark.parametrize("occurred_at", NOT_UTC, ids=["naive", "plus-07"])
def test_event_built_with_non_utc_time_is_refused(occurred_at: datetime) -> None:
    # Red when: a producer can build an event whose occurred_at is naive or not UTC.
    from ai_service.messaging.envelope import parse_event

    event = parse_event(example("user.deleted.v1"))
    with pytest.raises(ValidationError):
        rebuilt(event, occurred_at=occurred_at)
