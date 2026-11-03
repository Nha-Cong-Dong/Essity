"""T7.2b (US-13): sections ai-service flags `excluded` (front matter, preface, index) are stored
excluded, are not the learner's edit, never count and never become a suggestion."""

from datetime import date

from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.db.models import DocSection
from core_api.domain import outline as rules
from core_api.domain.outline import SectionRow
from core_api.domain.suggest import SubjectInput, suggest_for_subject
from core_api.handlers.document_indexed import parse_outline
from core_api.repositories.doc_section import DocSectionRepository
from core_api.repositories.study_ledger import StudyLedgerRepository
from core_api.services.outline import OutlineService
from documents.test_document_indexed import uploaded
from fake_storage import FakeStorage
from outline.test_handler import answer, node, run


def _flagged(title: str, parent: int | None, start: int, end: int) -> dict[str, object]:
    return node(title, parent, start, end) | {"excluded": True}


BODY = {
    "unit": "page",
    "nodes": [
        _flagged("Phần đầu sách", None, 1, 4),
        _flagged("Preface", None, 5, 8),
        node("Why", 1, 5, 6),
        node("Chương 1", None, 9, 40),
    ],
}


def test_excluded_flag_is_parsed_and_defaults_to_false() -> None:
    import json

    parsed = parse_outline(json.dumps(BODY).encode(), 40)
    assert parsed is not None
    assert [s.excluded for s in parsed[1]] == [True, True, False, False]
    plain = {"unit": "page", "nodes": [node("A", None, 1, 40)]}
    parsed = parse_outline(json.dumps(plain).encode(), 40)
    assert parsed is not None and parsed[1][0].excluded is False


def test_stored_excluded_sections_do_not_count_and_a_new_reading_may_replace_them(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    run(db_session, fake_storage, answer(fake_storage, document, BODY))

    rows = DocSectionRepository(db_session, user.id).of_document(document.id)
    assert [(r.title, r.excluded, r.source) for r in rows] == [
        ("Phần đầu sách", True, "bookmark"),
        ("Preface", True, "bookmark"),
        ("Why", False, "bookmark"),
        ("Chương 1", False, "bookmark"),
    ]
    gone = rules.excluded_ids([_section_row(r) for r in rows])
    assert {r.title for r in rows if r.id in gone} == {
        "Phần đầu sách",
        "Preface",
        "Why",
    }
    assert OutlineService(db_session, user.id).sections.touched(document.id) is False

    other = {"unit": "page", "nodes": [node("Other", None, 1, 40, "llm_toc")]}
    run(db_session, fake_storage, answer(fake_storage, document, other))
    rows = DocSectionRepository(db_session, user.id).of_document(document.id)
    assert [r.title for r in rows] == ["Other"]


def test_excluded_sections_and_their_children_never_become_the_next_item(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    run(db_session, fake_storage, answer(fake_storage, document, BODY))

    leaves = StudyLedgerRepository(db_session, user.id).leaves()[document.subject_id]
    assert [(leaf.title, leaf.excluded) for leaf in leaves] == [
        ("Phần đầu sách", True),
        ("Why", True),
        ("Chương 1", False),
    ]
    suggestion = suggest_for_subject(
        SubjectInput(document.subject_id, None, None, leaves), date(2026, 11, 3)
    )
    assert suggestion.leaf_title == "Chương 1"


def test_stats_leaves_under_an_excluded_section_are_excluded(
    db_session: Session, fake_storage: FakeStorage
) -> None:
    from core_api.repositories.stats import StatsRepository

    user = signed_in(db_session)[0]
    document = uploaded(db_session, user)
    run(db_session, fake_storage, answer(fake_storage, document, BODY))

    leaves = StatsRepository(db_session, user.id).leaves()[document.subject_id]
    assert sorted(leaf.excluded for leaf in leaves) == [False, True, True]


def _section_row(section: DocSection) -> SectionRow:
    return SectionRow(
        id=section.id,
        parent_id=section.parent_id,
        first_page=section.first_page or 0,
        last_page=section.last_page or 0,
        weight=section.weight,
        studied_weight=section.studied_weight,
        excluded=section.excluded,
    )
