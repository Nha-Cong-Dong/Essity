"""T9.8 / US-13: the OCR eval counts word errors on sample images, basic path against advanced
path, with a fake reader in CI. Thresholds stay unset until real data exists."""

from collections.abc import Callable
from pathlib import Path

from ai_service.tasks.read_notes_image import ReadPrompt
from evals.ocr.runner import (
    DEFAULT_CASES,
    EvalCase,
    load_cases,
    main,
    render,
    run,
    word_errors,
)


def test_word_errors_counts_edits_over_words() -> None:
    assert word_errors("a b c", "a b c") == 0
    assert word_errors("a b c", "a c") == 1
    assert word_errors("a b c", "a x c d") == 2
    assert word_errors("", "a b") == 2


def test_sample_cases_cover_the_three_hard_kinds() -> None:
    cases = load_cases(DEFAULT_CASES)
    assert {c.category for c in cases} == {"small_text", "table", "formula_text"}
    assert len({c.id for c in cases}) == len(cases)


def test_render_makes_an_image_of_the_case_size() -> None:
    import io

    from PIL import Image

    case = load_cases(DEFAULT_CASES)[0]
    assert Image.open(io.BytesIO(render(case))).size == (case.width, case.height)


def test_fake_run_advanced_has_fewer_errors_than_basic() -> None:
    report = run(load_cases(DEFAULT_CASES))
    assert report.basic_errors > report.advanced_errors == 0
    assert report.words > 0 and report.cases == len(load_cases(DEFAULT_CASES))
    assert not report.failed


def test_a_case_that_cannot_be_read_counts_all_its_words_and_is_listed() -> None:
    case = EvalCase(id="x", category="table", width=64, height=64, min_side=10, text="a b c")

    def broken(_case: EvalCase) -> Callable[[ReadPrompt], str]:
        def ask(_prompt: ReadPrompt) -> str:
            return "not json"

        return ask

    report = run([case], broken)
    assert report.basic_errors == report.advanced_errors == 3
    assert report.failed == ["x"]


def test_cli_writes_report_with_fake_provider_and_unset_thresholds(tmp_path: Path) -> None:
    out = tmp_path / "r" / "ocr.md"
    assert main(["--out", str(out)]) == 0
    text = out.read_text("utf-8")
    assert "provider: fake" in text
    assert "Word errors, basic path" in text and "Word errors, advanced path" in text
    assert "Threshold: not set" in text


def test_report_holds_numbers_and_ids_never_the_text(tmp_path: Path) -> None:
    out = tmp_path / "ocr.md"
    main(["--out", str(out)])
    text = out.read_text("utf-8")
    for case in load_cases(DEFAULT_CASES):
        assert case.text not in text
