"""Product rule (the user, 23/10; US-11 dropped): core-api never asks for or stores a GPA or a
starting point. Kept by scanning the source, as CONVENTIONS allows for a rule the user set (T1.22
plan E9): only the rule's own words, never the names of the removed code."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SOURCE = Path(__file__).resolve().parents[1] / "src" / "core_api"
# "gpa" as a name would write it (GPA, priorGpa, gpa_before, prior_gpa), not inside a word.
FORBIDDEN = [
    re.compile(r"GPA|Gpa|(?<![a-z])gpa"),
    re.compile(r"mốc ban đầu", re.IGNORECASE),
    re.compile(r"điểm xuất phát", re.IGNORECASE),
    re.compile(r"prior_ready_days"),
]


def grade_words(text: str) -> list[str]:
    return [match.group() for word in FORBIDDEN for match in word.finditer(text)]


def test_the_scan_reads_the_sources() -> None:
    assert (SOURCE / "api" / "me.py") in set(SOURCE.rglob("*.py"))


def test_no_grade_fields_in_core_api_source() -> None:
    # Red when: an endpoint, a model or a message asks for a GPA or a starting point again.
    hits = [
        f"{path.relative_to(SOURCE)}: {word}"
        for path in sorted(SOURCE.rglob("*.py"))
        for word in grade_words(path.read_text(encoding="utf-8"))
    ]
    assert hits == []


def test_scan_catches_a_planted_word() -> None:
    # Red when: the scan is too narrow (misses a cased or joined name) or too wide.
    assert grade_words("gpa_before: Decimal") == ["gpa"]
    assert sorted(grade_words("prior_gpa = 1; priorGpa; 'GPA hiện tại'")) == ["GPA", "Gpa", "gpa"]
    assert grade_words("prior_ready_days: int") == ["prior_ready_days"]
    assert grade_words("Mốc ban đầu, điểm xuất phát") == ["Mốc ban đầu", "điểm xuất phát"]
    assert grade_words("config_path = debug_page; baseline_css = 'items-baseline'") == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/baseline"),
        ("POST", "/v1/baseline"),
        ("PUT", "/v1/baseline"),
        ("POST", "/v1/baseline/skip"),
    ],
)
def test_baseline_endpoints_are_gone(client: TestClient, method: str, path: str) -> None:
    # Red when: the baseline router is mounted again.
    assert client.request(method, path).status_code == 404
