"""The three suites of T9.7a with scripted model replies (never a real model)."""

import json
from pathlib import Path
from typing import Any

import pytest

from ai_service.llm.quota import QuotaUnavailableError
from evals.draft_units.suite import SUITE as DRAFT
from evals.draft_units.suite import DraftCase
from evals.framework import cli
from evals.framework.gateway import ScriptedGateway
from evals.framework.runner import EvalCase, Scored, compute_metrics, load_cases, run_suite
from evals.generate_similar.suite import SUITE as SIMILAR
from evals.generate_similar.suite import LikeCase
from evals.link_question.suite import SUITE as LINK
from evals.link_question.suite import LinkCase, LinkRequest, LinkResult, make_suite


def run_one(suite: Any, case: Any, *replies: str | Exception) -> Scored | None:
    result = run_suite(suite, [case], lambda c: ScriptedGateway(list(replies)))
    return result.outcomes[case.id].scored


def unit(title: str, quote: str, page: str = "D1.p1") -> dict[str, Any]:
    return {
        "title": title,
        "summary": "s",
        "kind": "concept",
        "merge_into": None,
        "lineage": [],
        "anchors": [{"page": page, "quote": quote}],
    }


TEXT = "Mitochondria are the site of cellular respiration in eukaryotic cells."


def draft_case(**kw: Any) -> DraftCase:
    base: dict[str, Any] = {
        "id": "d",
        "docs": [{"name": "Bio", "pages": [TEXT]}],
        "expected": [{"quote": "site of cellular respiration"}],
    }
    base.update(kw)
    return DraftCase.model_validate(base)


def test_draft_exact_match_is_a_hit() -> None:
    reply = json.dumps({"units": [unit("Mito", "site of cellular respiration")]})
    scored = run_one(DRAFT, draft_case(), reply)
    assert scored is not None and scored.hit
    assert scored.counts == {"recall": (1, 1), "precision": (1, 1)}


def test_draft_split_idea_lowers_precision_not_recall() -> None:
    reply = json.dumps(
        {"units": [unit("A", "site of cellular respiration"), unit("B", "cellular respiration in")]}
    )
    scored = run_one(DRAFT, draft_case(), reply)
    assert scored is not None and not scored.hit
    assert scored.counts == {"recall": (1, 1), "precision": (1, 2)}


def test_draft_missing_unit_lowers_recall() -> None:
    case = draft_case(expected=[{"quote": "site of cellular"}, {"quote": "eukaryotic cells"}])
    reply = json.dumps({"units": [unit("A", "site of cellular respiration")]})
    scored = run_one(DRAFT, case, reply)
    assert scored is not None
    assert scored.counts["recall"] == (1, 2)


def test_draft_pending_ai_counts_as_total_miss() -> None:
    scored = run_one(DRAFT, draft_case(), QuotaUnavailableError())
    assert scored is not None and not scored.hit
    assert scored.counts == {"recall": (0, 1), "precision": (0, 0)}


def test_draft_case_needs_some_input() -> None:
    with pytest.raises(ValueError, match="documents or notes"):
        DraftCase.model_validate({"id": "x", "expected": []})


def like_case(**kw: Any) -> LikeCase:
    base: dict[str, Any] = {
        "id": "g",
        "samples": ["Explain how the cell membrane controls what enters the cell."],
        "cards": ["Osmosis moves water across a membrane.", "Mitochondria produce ATP."],
        "expected": {"status": "ok", "min_kept": 1, "leak_markers": ["photosynthesis"]},
    }
    base.update(kw)
    return LikeCase.model_validate(base)


def candidate(prompt: str) -> dict[str, Any]:
    return {"prompt": prompt, "reference_answer": "a", "rubric": "r", "cards": ["C2"]}


JUDGED = json.dumps(
    {"verdicts": [{"candidate": "Q1", "j1": True, "j2": True, "j3": True, "j4": True, "j5": True}]}
)


def test_similar_kept_question_is_a_hit() -> None:
    gen = json.dumps({"candidates": [candidate("Describe the role number one of mitochondria")]})
    scored = run_one(SIMILAR, like_case(), gen, JUDGED)
    assert scored is not None and scored.hit
    assert scored.counts == {"status": (1, 1), "leak_free": (1, 1)}


def test_similar_kept_off_source_question_is_a_leak() -> None:
    gen = json.dumps({"candidates": [candidate("Describe how photosynthesis feeds a plant cell")]})
    scored = run_one(SIMILAR, like_case(), gen, JUDGED)
    assert scored is not None and not scored.hit
    assert scored.counts["leak_free"] == (0, 1)


def test_similar_wrong_status_is_a_miss() -> None:
    scored = run_one(SIMILAR, like_case(), "not json")
    assert scored is not None and not scored.hit
    assert scored.counts["status"] == (0, 1)


def link_case(**kw: Any) -> LinkCase:
    base: dict[str, Any] = {
        "id": "l",
        "question": "How does water move?",
        "cards": [{"id": "c1", "title": "Osmosis"}, {"id": "c2", "title": "ATP"}],
        "expected": ["c1"],
    }
    base.update(kw)
    return LinkCase.model_validate(base)


class _Prompt:
    system = "s"
    user = "u"
    output_schema: dict[str, Any] = {}


def fake_link(request: LinkRequest, ask: Any) -> LinkResult:
    return LinkResult(json.loads(ask(_Prompt()))["cards"])


def test_link_unwired_task_is_an_error_not_a_pass() -> None:
    result = run_suite(LINK, [link_case()], lambda c: ScriptedGateway(["x"]))
    assert result.outcomes["l"].error == "TaskNotWiredError"
    assert compute_metrics(result).hit_rate == 0.0


def test_link_exact_and_extra_card() -> None:
    suite = make_suite(fake_link)
    exact = run_one(suite, link_case(), json.dumps({"cards": ["c1"]}))
    assert exact is not None and exact.hit
    extra = run_one(suite, link_case(), json.dumps({"cards": ["c1", "c2"]}))
    assert extra is not None and not extra.hit
    assert extra.counts == {"recall": (1, 1), "precision": (1, 2)}


def test_link_label_naming_a_missing_card_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    path.write_text(json.dumps(link_case(expected=["zzz"]).model_dump()) + "\n", "utf-8")
    with pytest.raises(ValueError, match="not in cards"):
        load_cases(make_suite(fake_link), path)


@pytest.mark.parametrize("name", ["draft_units", "generate_similar", "link_question"])
def test_sample_files_load(name: str) -> None:
    loaded = load_cases(cli.SUITES[name], cli.default_cases(name))
    assert loaded and all(isinstance(c, EvalCase) for c in loaded)


@pytest.mark.parametrize("suite", [DRAFT, SIMILAR])
def test_sample_cases_run_clean_with_their_fake_replies(suite: Any) -> None:
    loaded = load_cases(suite, cli.default_cases(suite.name))
    result = run_suite(suite, loaded, lambda c: ScriptedGateway(c.fake_replies))
    assert all(o.error is None for o in result.outcomes.values())
    assert len(result.outcomes) == len(loaded)
