"""T5.2 (US-03 AC3 ladder, PRD AC3, Q19 tạm): which question level a unit may be asked at. Pure."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core_api.domain.ladder import (
    LadderConfig,
    LadderQuestion,
    choose_for_unit,
    is_eligible,
    load_ladder_config,
)

CONFIG = LadderConfig(version=1, min_correct_level1=1, min_correct_level2=1)
A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
T0 = datetime(2026, 11, 1, tzinfo=UTC)


def question(level: int, *units: uuid.UUID, age: int = 0) -> LadderQuestion:
    return LadderQuestion(uuid.uuid4(), level, frozenset(units), T0 - timedelta(days=age))


# US-03 AC3. Red when: a level-1 question is ever held back.
def test_us03_ac3_level_one_is_always_eligible() -> None:
    assert is_eligible(question(1, A), {}, CONFIG)


# US-03 AC3. Red when: level 2 opens before a Correct at level 1, or stays shut after one, or
# a Correct on one unit opens it for another (every unit of the question counts).
def test_us03_ac3_level_two_needs_a_correct_at_level_one_for_each_unit() -> None:
    assert not is_eligible(question(2, A), {}, CONFIG)
    assert not is_eligible(question(2, A), {(A, 2): 5}, CONFIG)  # wrong level does not count
    assert is_eligible(question(2, A), {(A, 1): 1}, CONFIG)
    assert not is_eligible(question(2, A, B), {(A, 1): 1}, CONFIG)
    assert is_eligible(question(2, A, B), {(A, 1): 1, (B, 1): 3}, CONFIG)


# US-03 AC3. Red when: level 3 opens with one unit short at level 2, or on level-1 results.
def test_us03_ac3_level_three_needs_every_unit_correct_at_level_two() -> None:
    q = question(3, A, B, C)
    assert not is_eligible(q, {(A, 1): 9, (B, 1): 9, (C, 1): 9}, CONFIG)
    assert not is_eligible(q, {(A, 2): 1, (B, 2): 1}, CONFIG)
    assert is_eligible(q, {(A, 2): 1, (B, 2): 1, (C, 2): 1}, CONFIG)


# US-03 AC3. Red when: a question with no unit passes above level 1 (nothing was ever answered).
def test_us03_ac3_a_question_without_units_stays_at_level_one() -> None:
    assert not is_eligible(question(2), {}, CONFIG)
    assert not is_eligible(question(3), {}, CONFIG)


# US-03 AC3, Q19 tạm. Red when: thresholds are hard-coded: the same history gives other answers
# under another config, with no code change.
def test_us03_ac3_thresholds_come_from_the_config() -> None:
    strict = LadderConfig(version=2, min_correct_level1=3, min_correct_level2=2)
    history = {(A, 1): 2, (A, 2): 1}
    assert is_eligible(question(2, A), history, CONFIG)
    assert not is_eligible(question(2, A), history, strict)
    assert is_eligible(question(3, A), history, CONFIG)
    assert not is_eligible(question(3, A), {(A, 2): 1}, strict)
    assert is_eligible(question(3, A), {(A, 2): 2}, strict)


# US-03 AC3. Red when: a unit goes back to recognition after it earned the next level, or an
# ineligible higher question is chosen.
def test_us03_ac3_choose_the_highest_eligible_level_for_a_unit() -> None:
    l1, l2, l3 = question(1, A), question(2, A), question(3, A, B)
    pool = [l1, l2, l3]
    assert choose_for_unit(A, pool, {}, CONFIG) == l1
    assert choose_for_unit(A, pool, {(A, 1): 1}, CONFIG) == l2
    assert choose_for_unit(A, pool, {(A, 1): 1, (A, 2): 1}, CONFIG) == l2  # B not yet at level 2
    both = {(A, 1): 1, (A, 2): 1, (B, 2): 1}
    assert choose_for_unit(A, pool, both, CONFIG) == l3


# US-03 AC3. Red when: the choice among equal levels is not the oldest question (stable), or a
# question of other units is picked.
def test_us03_ac3_same_level_takes_the_oldest_and_only_this_units_questions() -> None:
    old, new, other = question(1, A, age=5), question(1, A, age=1), question(1, B, age=9)
    assert choose_for_unit(A, [new, other, old], {}, CONFIG) == old


# US-03 AC3. Red when: a unit whose only questions are above its level is dropped from today:
# it falls back to its lowest level.
def test_us03_ac3_never_drops_a_unit_without_an_eligible_question() -> None:
    l2, l3 = question(2, A), question(3, A)
    assert choose_for_unit(A, [l3, l2], {}, CONFIG) == l2
    assert choose_for_unit(A, [], {}, CONFIG) is None


# US-03 AC3, Q19 tạm. Red when: the shipped file is missing, unversioned, or not the temporary
# PRD values.
def test_us03_ac3_the_shipped_config_holds_the_temporary_values() -> None:
    config = load_ladder_config()
    assert config == LadderConfig(version=1, min_correct_level1=1, min_correct_level2=1)


# Red when: editing the JSON (no code) does not change the loaded thresholds.
def test_us03_ac3_editing_the_file_changes_the_thresholds(tmp_path: Path) -> None:
    path = tmp_path / "ladder.json"
    path.write_text(json.dumps({"version": 7, "min_correct_level1": 2, "min_correct_level2": 3}))
    assert load_ladder_config(path) == LadderConfig(7, 2, 3)


@pytest.mark.parametrize(
    "body",
    [
        {"version": 1, "min_correct_level1": 0, "min_correct_level2": 1},
        {"version": 1, "min_correct_level1": 1},
        {"min_correct_level1": 1, "min_correct_level2": 1},
        {"version": 1, "min_correct_level1": "1", "min_correct_level2": 1},
        {"version": 1, "min_correct_level1": True, "min_correct_level2": 1},
    ],
)
def test_us03_ac3_a_malformed_config_is_refused(tmp_path: Path, body: dict[str, object]) -> None:
    path = tmp_path / "ladder.json"
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        load_ladder_config(path)
