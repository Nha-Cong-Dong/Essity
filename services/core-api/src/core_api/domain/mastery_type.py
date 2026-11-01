"""Per-type mastery summary and the versioned formula file (T8.6b, US-16 AC4-AC8). Pure.

The formulas live in `mastery_formulas.json`: a new version is a new entry there (and `current`),
not a code change. `summarize` turns one type's attempts into what the screen shows.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, fields
from importlib import resources
from typing import Any

from core_api.domain.mastery import (
    DEFAULT_CONFIG,
    MasteryConfig,
    Sensitivity,
    TypeAttempt,
    mastery,
    mastery_line,
    reference,
    sensitivity,
    sensitivity_line,
)


class UnknownFormulaVersionError(LookupError):
    """The formula file has no such version."""


def load_config_from(raw: str, version: str | None = None) -> MasteryConfig:
    """A config from the formula file's text; unknown keys are refused (a typo is not silent)."""
    doc: Any = json.loads(raw)
    wanted = version or doc["current"]
    versions: dict[str, dict[str, Any]] = doc["versions"]
    if wanted not in versions:
        raise UnknownFormulaVersionError(wanted)
    known = {f.name for f in fields(MasteryConfig)} - {"version"}
    values = versions[wanted]
    extra = set(values) - known
    if extra:
        raise ValueError(f"unknown formula keys: {sorted(extra)}")
    return MasteryConfig(version=wanted, **values)


def load_config(version: str | None = None) -> MasteryConfig:
    raw = (resources.files("core_api.domain") / "mastery_formulas.json").read_text("utf-8")
    return load_config_from(raw, version)


@dataclass(frozen=True)
class TypeSummary:
    mastery: float | None
    attempts_counted: int
    mastery_line: str
    reference_seconds: float
    ref_origin: str  # default | rubric | learner_median | user
    sensitivity: Sensitivity
    sensitivity_line: str
    formula_version: str


def summarize(
    base_seconds: float,
    base_origin: str,
    attempts: Sequence[TypeAttempt],
    config: MasteryConfig = DEFAULT_CONFIG,
) -> TypeSummary:
    """`attempts` oldest first. The reference is the type's own (`base_seconds`, `base_origin`)
    until the learner has enough correct timed attempts, then their median; a reference the
    learner set (`user`) is never replaced."""
    learner = reference(1, attempts, config)
    if base_origin != "user" and learner.origin == "learner":
        seconds, origin = learner.seconds, "learner_median"
    else:
        seconds, origin = max(base_seconds, 1.0), base_origin
    counted = min(len(attempts), config.window)
    value = mastery(attempts, config)
    category = sensitivity(attempts, seconds, config)
    return TypeSummary(
        mastery=value,
        attempts_counted=counted,
        mastery_line=mastery_line(value, counted),
        reference_seconds=seconds,
        ref_origin=origin,
        sensitivity=category,
        sensitivity_line=sensitivity_line(category, seconds),
        formula_version=config.version,
    )
