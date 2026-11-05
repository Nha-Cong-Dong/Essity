"""G2: the chunk prompt (v2) asks for one blended card per idea from textbook + slides + notes.

Fake model only: these tests check the prompt text and that a blended unit with an anchor in each
source keeps all of its anchors (the merge itself is the model's job, the code keeps the evidence).
"""

from ai_service.tasks.chunk_units import PROMPT_VERSION, chunk_units, load_prompt

from .helpers import NOTES, Q1, FakeAsk, output, request, unit_json

NOTE_QUOTE = "ty the la noi hop ho hap te bao"


def test_g2_prompt_v2_asks_for_one_blended_card() -> None:
    assert PROMPT_VERSION == "v3"
    text = load_prompt().text
    for needle in ("ONE card per idea", "Merge:", "Add:", "Drop duplicates", "Bite-size"):
        assert needle in text


def test_g2_blended_unit_keeps_an_anchor_from_each_source() -> None:
    assert NOTE_QUOTE in NOTES
    ask = FakeAsk(
        output(
            unit_json(
                title="Ty the",
                summary="Ty the la noi hop ho hap, tao ATP.",
                anchors=[("D1.p1", Q1), ("notes", NOTE_QUOTE)],
            )
        )
    )
    result = chunk_units(request(), ask)
    assert len(result.new_units) == 1
    sources = {a.source for a in result.new_units[0].anchors}
    assert sources == {"document", "notes"}
    # The prompt the model got is the v2 one, and carries both the page and the notes.
    assert "ONE card per idea" in ask.prompts[0].system
    assert 'kind="notes"' in ask.prompts[0].user and 'kind="page"' in ask.prompts[0].user


# Red when: the card generator stops asking for Markdown and LaTeX maths in $...$ (CARD-MD).
def test_prompt_v3_asks_for_markdown_and_latex_in_dollars() -> None:
    assert PROMPT_VERSION == "v3"
    text = load_prompt().text
    for needle in ("Markdown", "$...$", r"\mid", r"\cdots", "never converted to LaTeX or Markdown"):
        assert needle in text
