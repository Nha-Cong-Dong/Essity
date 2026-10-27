from pathlib import Path

import pytest

from evals.grade.runner import DEFAULT_CASES, main
from evals.grade.schema import load_cases


def test_sample_cases_are_a_valid_injection_set() -> None:
    cases = load_cases(DEFAULT_CASES)
    assert len(cases) == 5
    assert {c.category for c in cases} == {"injection"}


def test_cli_writes_report_with_fake_provider(tmp_path: Path) -> None:
    # The fixture environment has a database URL nothing listens on: the run needs none.
    report = tmp_path / "out" / "report.md"
    assert main(["--out", str(report)]) == 0
    text = report.read_text("utf-8")
    assert "provider: fake" in text
    assert "Stability over 3 runs" in text


def test_sample_injection_cases_keep_their_labels_with_the_fake_grader(tmp_path: Path) -> None:
    # AC7 for the harness: with the fake grader no injection case is graded above its label.
    report = tmp_path / "report.md"
    main(["--out", str(report)])
    text = report.read_text("utf-8")
    assert "| injection | 5 | 5 |" in text
    assert "| Label match, overall (AC4) | 100.0% |" in text


def test_cli_refuses_anthropic_without_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        main(["--provider", "anthropic", "--out", str(tmp_path / "r.md")])
    assert not (tmp_path / "r.md").exists()


def test_cli_refuses_unpriced_model_and_bad_ceiling(tmp_path: Path) -> None:
    out = tmp_path / "r.md"
    assert main(["--model", "no-such-model", "--out", str(out)]) == 2
    assert main(["--max-cost-usd", "nan", "--out", str(out)]) == 2
    assert not out.exists()
