"""Event contracts (T4.1, ADR-0006), checked from ai-service's side.

Reads `contracts/events/` from the repository, never imports core-api (ADR-0003). ai-service's own
Pydantic models must take every valid example and refuse every invalid one. The check of these
models against the JSON Schemas themselves comes with the `jsonschema` dev dependency.
"""

import json
from pathlib import Path
from typing import Any, cast, get_args

import pytest
from pydantic import ValidationError

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "events"
EXAMPLES = CONTRACTS / "examples"

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
    envelope = cast(dict[str, Any], json.loads((CONTRACTS / "envelope.schema.json").read_text()))
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
