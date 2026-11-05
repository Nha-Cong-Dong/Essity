"""QA-Q11 edge cases: model ideas named by label or by words (US-05 AC9, per-idea result)."""

import unicodedata

import pytest

from ai_service.tasks import grade_practice as gp

from .helpers import FakeAsk, idea, reply, request

_VI = ["Ba bước bắt tay", "Gói SYN đến trước"]
_VI_ANSWER = "Có ba bước bắt tay, gói SYN đến trước."


def _vi(**kw: object) -> gp.PracticeGradeRequest:
    return request(rubric=_VI, answer=_VI_ANSWER, **kw)


def test_vietnamese_words_in_nfd_match_the_nfc_rubric() -> None:
    # Red when: the words are not NFC-normalised before comparing, so a model reply in
    # decomposed form (marks as separate code points) never matches and every grade fails.
    words = unicodedata.normalize("NFD", _VI[1])
    assert words != _VI[1]
    text = reply(idea(words, "no"), idea("R1", "yes", "ba bước bắt tay"))
    result = gp.grade_practice(_vi(), FakeAsk(text))
    assert result.status == "ok"
    assert [i.verdict for i in result.ideas] == ["correct", "incorrect"]


def test_nfd_rubric_matches_nfc_words() -> None:
    # Red when: only the model side is normalised (rubric stored decomposed).
    rubric = [unicodedata.normalize("NFD", t) for t in _VI]
    text = reply(idea(_VI[0], "yes", "ba bước bắt tay"), idea(_VI[1], "no"))
    result = gp.grade_practice(request(rubric=rubric, answer=_VI_ANSWER), FakeAsk(text))
    assert result.status == "ok"
    assert [i.verdict for i in result.ideas] == ["correct", "incorrect"]


@pytest.mark.parametrize("words", ["Ba buoc bat tay", "Ba bước bat tay", "Bà bước bắt tay"])
def test_words_differing_in_vietnamese_marks_do_not_match(words: str) -> None:
    # Red when: marks are stripped (or compared loosely), so a different word ("bà" vs "ba")
    # is taken for the rubric idea and graded as that idea.
    text = reply(idea(words, "yes", "ba bước bắt tay"), idea("R2", "no"))
    result = gp.grade_practice(_vi(), FakeAsk(text))
    assert result.status == "failed" and result.failure == gp.FAIL_MALFORMED


def test_vietnamese_upper_case_matches() -> None:
    # Red when: case folding is dropped (Vietnamese capitals such as "Đ", "Ắ").
    rubric = ["Đóng kết nối", "Gói SYN đến trước"]
    text = reply(idea("ĐÓNG KẾT NỐI", "no"), idea("gói syn đến trước", "yes", "gói SYN"))
    result = gp.grade_practice(request(rubric=rubric, answer=_VI_ANSWER), FakeAsk(text))
    assert result.status == "ok"
    assert [i.verdict for i in result.ideas] == ["incorrect", "correct"]


def test_rubric_ideas_differing_only_in_case_cannot_be_named_by_words() -> None:
    # Two ideas equal once normalised: words cannot tell them apart. Red when: the second is
    # silently assigned (e.g. last match wins) instead of refusing the reply.
    rubric = ["TCP", "tcp"]
    by_words = reply(idea("tcp", "yes", "Client gui SYN"), idea("TCP", "no"))
    assert gp.grade_practice(request(rubric=rubric), FakeAsk(by_words)).failure == (
        gp.FAIL_MALFORMED
    )
    by_label = reply(idea("R2", "no"), idea("R1", "yes", "Client gui SYN"))
    result = gp.grade_practice(request(rubric=rubric), FakeAsk(by_label))
    assert result.status == "ok"
    assert [i.verdict for i in result.ideas] == ["correct", "incorrect"]


@pytest.mark.parametrize(
    ("label", "ok"),
    [("R1", True), ("Three steps", True), ("three steps!", True), ("R2", False), ("R0", False)],
)
def test_one_idea_rubric(label: str, ok: bool) -> None:
    # Red when: the enum or the label check is off by one for a single-idea rubric.
    req = request(rubric=["Three steps"])
    schema = gp.build_prompt(req).output_schema
    assert schema["$defs"]["LlmIdea"]["properties"]["idea"]["enum"] == ["R1"]
    result = gp.grade_practice(req, FakeAsk(reply(idea(label, "yes", "Client gui SYN"))))
    if ok:
        assert result.status == "ok" and result.overall == "correct"
    else:
        assert result.status == "failed" and result.failure == gp.FAIL_MALFORMED


def test_one_idea_by_label_and_the_other_by_words() -> None:
    # Red when: a reply mixing a label and words is refused, or the words idea takes the
    # labelled idea's verdict.
    text = reply(idea("Names SYN, SYN-ACK, ACK", "no"), idea("R1", "yes", "Client gui SYN"))
    result = gp.grade_practice(request(), FakeAsk(text))
    assert result.status == "ok"
    assert [i.verdict for i in result.ideas] == ["correct", "incorrect"]


def test_same_idea_by_label_and_by_words_is_malformed() -> None:
    # R2 given twice (once as "R2", once by its words), R1 missing.
    text = reply(idea("R2", "no"), idea("Names SYN, SYN-ACK, ACK", "yes", "Client gui SYN"))
    assert gp.grade_practice(request(), FakeAsk(text)).failure == gp.FAIL_MALFORMED


def test_same_idea_by_label_and_by_words_with_all_labels_present_is_malformed() -> None:
    # Red when: the once-each check is dropped; three replies for two ideas then pass with
    # whichever R1 comes last.
    text = reply(
        idea("R1", "yes", "Client gui SYN"),
        idea("R2", "no"),
        idea("three steps", "no"),
    )
    assert gp.grade_practice(request(), FakeAsk(text)).failure == gp.FAIL_MALFORMED


@pytest.mark.parametrize(
    "words",
    [
        "Three",  # prefix
        "steps",  # suffix
        "Three steps and more",  # rubric idea inside longer words
        "Names SYN",  # part of R2
        "",  # empty
        "   ",  # blank
        "R1 Three steps",  # label plus words
        "r1",  # label in lower case is not a label
        "R01",  # zero-padded label
    ],
)
def test_partial_or_odd_names_are_malformed(words: str) -> None:
    # Red when: matching is loosened (substring, prefix, int parsing of labels), so a reply
    # that does not name the rubric idea exactly gets graded as that idea.
    text = reply(idea(words, "yes", "Client gui SYN"), idea("R2", "no"))
    result = gp.grade_practice(request(), FakeAsk(text))
    assert result.status == "failed" and result.failure == gp.FAIL_MALFORMED


def test_schema_per_request_is_a_copy() -> None:
    # Red when: _schema_for edits OUTPUT_SCHEMA in place, so one request's labels leak into the
    # next (a 1-idea request after a 3-idea one would still allow R2, R3).
    three = gp.build_prompt(request(rubric=["a", "b", "c"])).output_schema
    one = gp.build_prompt(request(rubric=["a"])).output_schema
    assert three["$defs"]["LlmIdea"]["properties"]["idea"]["enum"] == ["R1", "R2", "R3"]
    assert one["$defs"]["LlmIdea"]["properties"]["idea"]["enum"] == ["R1"]
    assert "enum" not in gp.OUTPUT_SCHEMA["$defs"]["LlmIdea"]["properties"]["idea"]
