"""T7.7 / PLAN "Xong khi": the draft eval runs in CI with the fake provider (US-02b AC2).

The real numbers wait for an API key and T9.7; this only proves the harness runs end to end."""

from pathlib import Path

from evals.framework import cli


def test_draft_units_eval_with_fake_reader_runs_in_ci(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    assert cli.main(["--suite", "draft_units", "--provider", "fake", "--out", str(out)]) == 0
    text = out.read_text("utf-8")
    assert "provider: fake" in text and "recall" in text and "Errors (counted as a miss): 0" in text
