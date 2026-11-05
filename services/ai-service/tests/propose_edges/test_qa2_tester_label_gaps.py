"""QA2-FSRS tester, second pass: gaps the mutation run found in `check_edges` with source labels.
Pure `check_edges`, no model and no database."""

import json
import uuid

import pytest

from ai_service.tasks.propose_edges import check_edges
from ai_service.tasks.question_models import QuestionUnit

SOURCE_QUOTE = "TCP opens a connection with a three-way handshake."
FIRST = "IP addresses every packet separately."
SECOND = "A router forwards a packet by its destination address."


def unit(*quotes: str) -> QuestionUnit:
    return QuestionUnit.model_validate(
        {"unit_id": str(uuid.uuid4()), "title": "T", "summary": "S.", "quotes": list(quotes)}
    )


def labels() -> dict[str, QuestionUnit]:
    return {"S": unit(SOURCE_QUOTE), "C1": unit(FIRST, SECOND)}


def text(*evidence: tuple[str, str]) -> str:
    edge = {
        "kind": "prerequisite",
        "from": "S",
        "to": "C1",
        "evidence": [{"card": card, "quote": quote} for card, quote in evidence],
    }
    return json.dumps({"edges": [edge]})


def test_the_source_card_is_reached_by_its_own_label() -> None:
    # Red when: the label pattern knows only candidates (`C<n>.A<n>`), not the source (`S.A1`),
    # though the prompt labels the source's blocks `S.A1` too.
    known = labels()
    edges, dropped = check_edges(text(("S.A1", SOURCE_QUOTE)), known)
    assert dropped == 0
    assert [e.unit_id for e in edges[0].evidence] == [known["S"].unit_id]


def test_the_source_label_checks_its_own_anchor_only() -> None:
    # Red when: `S.A1` opens the anchors of the edge's other card.
    edges, dropped = check_edges(text(("S.A1", FIRST)), labels())
    assert edges == [] and dropped == 1


@pytest.mark.parametrize("card", ["C1.A1", "C1", "S.A1"])
@pytest.mark.parametrize("quote", ["", "   ", "\n\t"])
def test_an_empty_quote_is_no_evidence(card: str, quote: str) -> None:
    # Red when: an empty (or whitespace) quote counts: "" is a substring of every anchor, so the
    # model could back any edge with nothing.
    edges, dropped = check_edges(text((card, quote)), labels())
    assert edges == [] and dropped == 1


def test_one_bad_label_quote_drops_the_whole_edge() -> None:
    # Red when: an edge stands on its good quote while another quote names the wrong anchor.
    edges, dropped = check_edges(text(("C1.A1", FIRST), ("C1.A1", SECOND)), labels())
    assert edges == [] and dropped == 1
