"""T4.17: `unit_lineage`, `knowledge_unit.section_id` and `anchor.document_id` (us-02b §9 #3)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models import Anchor, KnowledgeUnit, Subject, UnitLineage, User
from fake_storage import FakeStorage
from isolation import assert_isolated
from sessions.session_helpers import indexed_document, subject_of


def unit_of(db: Session, user: User, subject: Subject, title: str = "Mảnh") -> KnowledgeUnit:
    unit = KnowledgeUnit(
        user_id=user.id,
        subject_id=subject.id,
        title=title,
        summary="s",
        kind="concept",
        run_id=uuid.uuid4(),
    )
    db.add(unit)
    db.flush()
    return unit


def rejected(db: Session, row: object) -> None:
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(row)
        db.flush()


def test_unit_lineage_isolated(db_session: Session, two_users: tuple[User, User]) -> None:
    from core_api.repositories.base import UserScopedRepository

    alice, bob = two_users
    subject = subject_of(db_session, alice)
    old, new = unit_of(db_session, alice, subject, "a"), unit_of(db_session, alice, subject, "b")

    class Lineages(UserScopedRepository[UnitLineage]):
        model = UnitLineage

    assert_isolated(
        db_session,
        Lineages,
        alice,
        bob,
        lambda repo: repo.add(
            UnitLineage(old_unit_id=old.id, new_unit_id=new.id, run_id=uuid.uuid4())
        ),
    )


def test_lineage_refuses_self_duplicate_and_foreign_units(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    sa_, sb = subject_of(db_session, alice), subject_of(db_session, bob)
    a1, a2 = unit_of(db_session, alice, sa_, "a1"), unit_of(db_session, alice, sa_, "a2")
    b1 = unit_of(db_session, bob, sb)
    run = uuid.uuid4()
    rejected(
        db_session, UnitLineage(user_id=alice.id, old_unit_id=a1.id, new_unit_id=a1.id, run_id=run)
    )
    rejected(
        db_session, UnitLineage(user_id=alice.id, old_unit_id=a1.id, new_unit_id=b1.id, run_id=run)
    )
    rejected(
        db_session,
        UnitLineage(
            user_id=alice.id, old_unit_id=a1.id, new_unit_id=a2.id, confidence=1.5, run_id=run
        ),
    )
    db_session.add(UnitLineage(user_id=alice.id, old_unit_id=a1.id, new_unit_id=a2.id, run_id=run))
    db_session.flush()
    rejected(
        db_session, UnitLineage(user_id=alice.id, old_unit_id=a1.id, new_unit_id=a2.id, run_id=run)
    )


def test_anchor_document_must_be_the_users_and_only_for_document_source(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    storage = FakeStorage()
    subject = subject_of(db_session, alice)
    other = subject_of(db_session, bob)
    mine = indexed_document(db_session, storage, alice, subject)
    theirs = indexed_document(db_session, storage, bob, other, sha="ef" * 32)
    unit = unit_of(db_session, alice, subject)

    def anchor(**over: object) -> Anchor:
        values: dict[str, object] = {
            "user_id": alice.id,
            "unit_id": unit.id,
            "source": "document",
            "document_id": mine.id,
            "page_no": 3,
            "quote_text": "q",
            "run_id": uuid.uuid4(),
        } | over
        return Anchor(**values)

    db_session.add(anchor())
    db_session.add(anchor(document_id=None, page_no=None))  # seeded: no document
    db_session.flush()
    rejected(db_session, anchor(document_id=theirs.id))
    rejected(db_session, anchor(source="notes"))  # notes never point at a document
    db_session.execute(text("DELETE FROM document WHERE id = :i"), {"i": mine.id})
    assert (
        db_session.scalar(
            text("SELECT count(*) FROM anchor WHERE document_id = :i"), {"i": mine.id}
        )
        == 0
    )


def test_section_id_is_nullable(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, _ = two_users
    unit = unit_of(db_session, alice, subject_of(db_session, alice))
    assert unit.section_id is None
    unit.section_id = uuid.uuid4()
    db_session.flush()
