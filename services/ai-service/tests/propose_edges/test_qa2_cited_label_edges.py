"""QA2-FSRS tester: evidence cited by its source label (`C1.A2`) is checked against exactly that
anchor of that card. Pure `check_edges`, no model and no database."""

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


def labels(candidates: int = 1) -> dict[str, QuestionUnit]:
    out = {"S": unit(SOURCE_QUOTE), "C1": unit(FIRST, SECOND)}
    out.update({f"C{n}": unit(f"Quote of card {n}.") for n in range(2, candidates + 1)})
    return out


def text(card: str, quote: str, to: str = "C1") -> str:
    edge = {
        "kind": "prerequisite",
        "from": "S",
        "to": to,
        "evidence": [{"card": card, "quote": quote}],
    }
    return json.dumps({"edges": [edge]})


def test_the_second_anchor_is_reached_by_its_own_label() -> None:
    # Red when: `C1.A2` is read as the first anchor (index n instead of n - 1, or always 0).
    known = labels()
    edges, dropped = check_edges(text("C1.A2", SECOND), known)
    assert dropped == 0
    assert [e.unit_id for e in edges[0].evidence] == [known["C1"].unit_id]


@pytest.mark.parametrize(
    ("card", "quote"),
    [
        ("C1.A1", SECOND),  # the quote is in C1's second anchor, not the first it names
        ("C1.A2", FIRST),  # and the other way round
        ("C1.A0", SECOND),  # no anchor 0: must not wrap round to the last one
        ("C1.A3", FIRST),  # past the last anchor
        ("C1.A1x", FIRST),  # trailing junk is not a source label
        ("XC1.A1", FIRST),  # leading junk neither
    ],
)
def test_a_source_label_allows_only_its_own_anchor(card: str, quote: str) -> None:
    # Red when: a label opens every anchor of the card, wraps round on A0, or matches loosely.
    edges, dropped = check_edges(text(card, quote), labels())
    assert edges == [] and dropped == 1


def test_a_two_digit_candidate_label_is_a_source_label() -> None:
    # Red when: only C1..C9 are recognised; core-api sends up to ten candidates (MAX_CANDIDATES).
    known = labels(candidates=10)
    edges, dropped = check_edges(text("C10.A1", "Quote of card 10.", to="C10"), known)
    assert dropped == 0 and edges[0].evidence[0].unit_id == known["C10"].unit_id


def test_the_bare_card_label_still_searches_all_its_anchors() -> None:
    # Red when: the old form (`C1`) loses its anchors after the source-label change.
    edges, dropped = check_edges(text("C1", SECOND), labels())
    assert dropped == 0 and len(edges) == 1


@pytest.mark.parametrize("card", ["C2.A1", "C2"])
def test_a_real_card_outside_the_edge_gives_no_evidence(card: str) -> None:
    # Red when: a verbatim quote of a third card (sent, but not in this edge) backs the edge.
    edges, dropped = check_edges(text(card, "Quote of card 2."), labels(candidates=2))
    assert edges == [] and dropped == 1
