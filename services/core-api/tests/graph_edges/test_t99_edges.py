"""T9.9 (US-19 AC1, AC2, PLAN T9.9): the edges proposed after a Save. The AI is a double that counts
its calls (never a real API); the database is real."""

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.clients.ai_client import NotGraded
from core_api.clients.propose_edges_contract import (
    EdgeEvidenceReply,
    ProposedEdgeReply,
    ProposeEdgesReply,
)
from core_api.db.models import Anchor, KnowledgeUnit, Subject, UnitEdge, UnitSection, User
from core_api.domain.graph import PROPOSAL_BATCH_SIZE, EdgeKind
from core_api.handlers.unit_saved import AiUnavailableError
from core_api.services.unit_edges import (
    UnknownEdgeError,
    add_user_edge,
    propose_edges_for_unit,
    reject_edge,
)
from v2_rows import RUN, make_document, make_section, make_subject, make_unit

SAVED_QUOTE = "TCP mở kết nối bằng ba bước bắt tay."
OTHER_QUOTE = "IP đánh địa chỉ cho từng gói tin."


class FakeAi:
    """Counts calls. Answers what `reply_for` builds from the payload, or a fixed `reply`."""

    def __init__(self, kind: str = "prerequisite", quote: str | None = None) -> None:
        self.kind, self.quote = kind, quote
        self.payloads: list[dict[str, Any]] = []
        self.fixed: ProposeEdgesReply | NotGraded | None = None

    def propose_edges(self, payload: dict[str, Any]) -> ProposeEdgesReply | NotGraded:
        self.payloads.append(payload)
        if self.fixed is not None:
            return self.fixed
        first = payload["candidates"][0]
        quote = self.quote if self.quote is not None else first["quotes"][0]
        return reply(
            edge(
                uuid.UUID(payload["source"]["unit_id"]),
                uuid.UUID(first["unit_id"]),
                quote,
                self.kind,
                uuid.UUID(first["unit_id"]),
            )
        )


def edge(
    src: uuid.UUID, dst: uuid.UUID, quote: str, kind: str, owner: uuid.UUID
) -> ProposedEdgeReply:
    return ProposedEdgeReply(
        kind=kind,
        source_id=src,
        target_id=dst,
        evidence=[EdgeEvidenceReply(unit_id=owner, quote=quote)] if quote else [],
    )


def reply(*edges: ProposedEdgeReply, status: str = "ok") -> ProposeEdgesReply:
    return ProposeEdgesReply(
        status=status,  # pyright: ignore[reportArgumentType]
        prompt_version="v1",
        run_id=RUN,
        edges=list(edges),
    )


def card(
    db: Session, user: User, subject: Subject, quote: str | None = OTHER_QUOTE, **kw: Any
) -> KnowledgeUnit:
    unit = make_unit(db, user, subject, **{"status": "canonical"} | kw)
    if quote:
        db.add(
            Anchor(
                user_id=user.id,
                unit_id=unit.id,
                source="notes",
                quote_text=quote,
                run_id=RUN,
            )
        )
        db.flush()
    return unit


@pytest.fixture
def alice(two_users: tuple[User, User]) -> User:
    return two_users[0]


@pytest.fixture
def subject(db_session: Session, alice: User) -> Subject:
    return make_subject(db_session, alice)


def edges(db: Session, user: User) -> list[UnitEdge]:
    return list(db.scalars(select(UnitEdge).where(UnitEdge.user_id == user.id)))


def test_ac2_edge_with_a_real_quote_is_stored_active_with_its_evidence(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: a valid edge is lost, stored without its quote, or stored as something else.
    old, new = card(db_session, alice, subject), card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi()
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "created"
    [stored] = edges(db_session, alice)
    assert (stored.src_unit_id, stored.dst_unit_id, stored.kind) == (new.id, old.id, "prerequisite")
    assert (stored.origin, stored.status, stored.run_id) == ("ai", "active", RUN)
    assert stored.evidence == [{"unit_id": str(old.id), "quote": OTHER_QUOTE}]


def test_ac2_a_quote_that_is_not_in_the_anchors_makes_no_edge(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: evidence is trusted instead of checked against the anchors.
    card(db_session, alice, subject)
    new = card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi(quote="Câu này không có trong neo nào.")
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "none"
    assert edges(db_session, alice) == []


def test_ac2_no_evidence_no_edge(db_session: Session, alice: User, subject: Subject) -> None:
    # Red when: an edge without any quote is stored.
    card(db_session, alice, subject)
    new = card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi(quote="")
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "none"
    assert edges(db_session, alice) == []


def test_ac2_one_bad_quote_among_good_ones_voids_the_edge(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: an edge keeps going on one valid quote while another is invented.
    old, new = card(db_session, alice, subject), card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi()
    ai.fixed = reply(
        ProposedEdgeReply(
            kind="part_of",
            source_id=new.id,
            target_id=old.id,
            evidence=[
                EdgeEvidenceReply(unit_id=old.id, quote=OTHER_QUOTE),
                EdgeEvidenceReply(unit_id=old.id, quote="bịa"),
            ],
        )
    )
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "none"
    assert edges(db_session, alice) == []


def test_ac1_a_kind_outside_the_five_is_refused(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: a generic "related" kind can be stored.
    card(db_session, alice, subject)
    new = card(db_session, alice, subject, SAVED_QUOTE)
    assert propose_edges_for_unit(db_session, alice.id, new.id, FakeAi(kind="related")) == "none"
    assert edges(db_session, alice) == []


def test_ac2_two_cards_of_two_subjects_are_never_linked(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: the other subject's card is a candidate, or a reply naming it is stored.
    other = make_subject(db_session, alice, "Cơ sở dữ liệu")
    far = card(db_session, alice, other)
    new = card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi()
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "no_candidates"
    assert ai.payloads == []
    near = card(db_session, alice, subject)
    ai.fixed = reply(edge(new.id, far.id, OTHER_QUOTE, "prerequisite", far.id))
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "none"
    assert near.id != far.id and edges(db_session, alice) == []


def test_ac2_another_users_card_is_not_a_candidate(
    db_session: Session, two_users: tuple[User, User], alice: User, subject: Subject
) -> None:
    # Red when: candidates are read without the user scope.
    bob = two_users[1]
    card(db_session, bob, make_subject(db_session, bob))
    new = card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi()
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "no_candidates"
    assert propose_edges_for_unit(db_session, bob.id, new.id, ai) == "skipped"


def test_edge_must_touch_the_saved_card(db_session: Session, alice: User, subject: Subject) -> None:
    # Red when: an edge between two other cards is stored for this Save.
    a, b = card(db_session, alice, subject), card(db_session, alice, subject)
    new = card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi()
    ai.fixed = reply(edge(a.id, b.id, OTHER_QUOTE, "part_of", a.id))
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "none"


def test_resent_unit_saved_creates_no_duplicate_edge(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: a second run for the same card adds a second row.
    card(db_session, alice, subject)
    new = card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi()
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "created"
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "none"
    assert len(edges(db_session, alice)) == 1


def test_contrast_is_stored_once_whichever_card_is_saved_last(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: contrast is stored in both directions, or the database refuses the order.
    a, b = card(db_session, alice, subject), card(db_session, alice, subject)
    ai = FakeAi(kind="contrast")
    assert propose_edges_for_unit(db_session, alice.id, a.id, ai) == "created"
    assert propose_edges_for_unit(db_session, alice.id, b.id, ai) == "none"
    [stored] = edges(db_session, alice)
    assert str(stored.src_unit_id) < str(stored.dst_unit_id)


def test_a_removed_edge_is_not_proposed_again(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: a rejected edge comes back at the next Save.
    card(db_session, alice, subject)
    new = card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi()
    propose_edges_for_unit(db_session, alice.id, new.id, ai)
    [stored] = edges(db_session, alice)
    reject_edge(db_session, alice.id, stored.id)
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "none"
    [after] = edges(db_session, alice)
    assert after.status == "rejected"


def test_a_draft_or_retired_card_is_skipped_without_a_call(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: a card that is not saved asks the model.
    card(db_session, alice, subject)
    draft = card(db_session, alice, subject, status="draft")
    ai = FakeAi()
    assert propose_edges_for_unit(db_session, alice.id, draft.id, ai) == "skipped"
    assert propose_edges_for_unit(db_session, alice.id, uuid.uuid4(), ai) == "skipped"
    gone = card(db_session, alice, subject)
    gone.status = "retired"
    db_session.flush()
    assert propose_edges_for_unit(db_session, alice.id, gone.id, ai) == "skipped"
    assert ai.payloads == []


def test_model_calls_are_linear_in_the_number_of_cards(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: the calls of a Save grow with the cards already there (batches, not all pairs).
    ai = FakeAi()
    total = 3 * PROPOSAL_BATCH_SIZE
    for n in range(total):
        unit = card(db_session, alice, subject, f"Neo số {n}.")
        propose_edges_for_unit(db_session, alice.id, unit.id, ai)
    assert len(ai.payloads) == total - 1  # the first card has nobody to relate to
    assert max(len(p["candidates"]) for p in ai.payloads) == PROPOSAL_BATCH_SIZE


def test_candidates_sharing_a_section_come_first(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: the cards of the same outline section are not the ones compared.
    doc = make_document(db_session, alice, subject)
    section = make_section(db_session, alice, doc)
    friend = card(db_session, alice, subject)
    for _ in range(PROPOSAL_BATCH_SIZE + 2):
        card(db_session, alice, subject)  # newer, but elsewhere
    new = card(db_session, alice, subject, SAVED_QUOTE)
    for unit in (friend, new):
        db_session.add(
            UnitSection(
                user_id=alice.id, subject_id=subject.id, unit_id=unit.id, section_id=section.id
            )
        )
    db_session.flush()
    ai = FakeAi()
    propose_edges_for_unit(db_session, alice.id, new.id, ai)
    assert ai.payloads[0]["candidates"][0]["unit_id"] == str(friend.id)


def test_ai_down_is_retried_and_quota_is_not_an_error(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: an unreachable ai-service is swallowed (no retry) or the cap raises.
    card(db_session, alice, subject)
    new = card(db_session, alice, subject, SAVED_QUOTE)
    ai = FakeAi()
    ai.fixed = NotGraded("unavailable", "timeout")
    with pytest.raises(AiUnavailableError):
        propose_edges_for_unit(db_session, alice.id, new.id, ai)
    ai.fixed = NotGraded("quota", "quota_hard_cap")
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "pending_ai"
    ai.fixed = reply(status="failed")
    assert propose_edges_for_unit(db_session, alice.id, new.id, ai) == "failed"


@pytest.mark.parametrize("status", ["merged", "retired"])
def test_replaced_card_turns_its_edges_inactive(
    db_session: Session, alice: User, subject: Subject, status: str
) -> None:
    # Red when: a merged, split (original becomes merged) or retired card keeps active edges.
    old, new = card(db_session, alice, subject), card(db_session, alice, subject, SAVED_QUOTE)
    propose_edges_for_unit(db_session, alice.id, new.id, FakeAi())
    old.status = status
    db_session.flush()
    db_session.expire_all()
    [stored] = edges(db_session, alice)
    assert stored.status == "inactive"


def test_a_rejected_edge_stays_rejected_when_the_card_is_replaced(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: the trigger reopens or rewrites the learner's own decision.
    old, new = card(db_session, alice, subject), card(db_session, alice, subject, SAVED_QUOTE)
    propose_edges_for_unit(db_session, alice.id, new.id, FakeAi())
    reject_edge(db_session, alice.id, edges(db_session, alice)[0].id)
    old.status = "merged"
    db_session.flush()
    db_session.expire_all()
    assert edges(db_session, alice)[0].status == "rejected"


def test_user_edge_needs_no_evidence_but_stays_in_one_subject_and_one_account(
    db_session: Session, two_users: tuple[User, User], alice: User, subject: Subject
) -> None:
    # Red when: a learner's edge crosses subjects or accounts, or asks for evidence.
    a, b = card(db_session, alice, subject), card(db_session, alice, subject)
    made = add_user_edge(db_session, alice.id, EdgeKind.APPLIES_TO, a.id, b.id)
    assert (made.origin, made.status, made.evidence) == ("user", "active", [])
    assert add_user_edge(db_session, alice.id, EdgeKind.APPLIES_TO, a.id, b.id).id == made.id
    far = card(db_session, alice, make_subject(db_session, alice, "Cơ sở dữ liệu"))
    with pytest.raises(ValueError, match="cross_subject"):
        add_user_edge(db_session, alice.id, EdgeKind.PART_OF, a.id, far.id)
    with pytest.raises(UnknownEdgeError):
        add_user_edge(db_session, two_users[1].id, EdgeKind.PART_OF, a.id, b.id)
    with pytest.raises(UnknownEdgeError):
        reject_edge(db_session, two_users[1].id, made.id)


def test_suggestion_follows_a_proposed_prerequisite_until_the_card_is_replaced(
    db_session: Session, alice: User, subject: Subject
) -> None:
    # Red when: the study suggestion ignores an edge the Save made (PLAN T9.9, US-15 AC2), or keeps
    # following it after a card went away (an inactive edge).
    from core_api.repositories.study_ledger import StudyLedgerRepository

    doc = make_document(db_session, alice, subject)
    doc.role = "textbook"  # only the main textbook's sections are leaves
    first, second = (make_section(db_session, alice, doc, ord=i, title=f"M{i}") for i in range(2))
    needed = card(db_session, alice, subject)
    needs = card(db_session, alice, subject, SAVED_QUOTE)
    for unit, section in ((needs, first), (needed, second)):
        db_session.add(
            UnitSection(
                user_id=alice.id, subject_id=subject.id, unit_id=unit.id, section_id=section.id
            )
        )
    db_session.flush()
    ai = FakeAi(quote=OTHER_QUOTE)
    assert propose_edges_for_unit(db_session, alice.id, needs.id, ai) == "created"

    def prerequisites() -> tuple[uuid.UUID, ...]:
        leaves = StudyLedgerRepository(db_session, alice.id).leaves()[subject.id]
        return next(leaf.prerequisites for leaf in leaves if leaf.id == first.id)

    assert prerequisites() == (second.id,)
    needed.status = "merged"
    db_session.flush()
    assert prerequisites() == ()
