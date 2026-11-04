"""QA 05/11 (US-13, US-15): only the main textbook's sections are the leaves to study.

A question bank or an auxiliary file also gets a section row from the reader; counting them
made "Đã học x/N" (stats) disagree with the Đề cương (x/N-2) and put a bank page in "Tiếp theo".
"""

from sqlalchemy.orm import Session

from accounts import signed_in
from core_api.repositories.study_ledger import StudyLedgerRepository
from outline.outline_rows import document_in, subject_of, with_outline


def test_leaves_come_from_the_textbook_only(db_session: Session) -> None:
    user = signed_in(db_session)[0]
    subject = subject_of(db_session, user)
    textbook = document_in(db_session, user, subject, "Giáo trình")
    bank = document_in(db_session, user, subject, "Bộ câu hỏi", role="question_bank")
    extra = document_in(db_session, user, subject, "Slide", role="auxiliary")
    book_ids = {r.id for r in with_outline(db_session, user, textbook).values()}
    with_outline(db_session, user, bank)
    with_outline(db_session, user, extra)

    leaves = StudyLedgerRepository(db_session, user.id).leaves()[subject.id]

    assert {leaf.id for leaf in leaves} <= book_ids
    assert len(leaves) > 0
