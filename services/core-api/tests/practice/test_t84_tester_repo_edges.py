"""T8.4 tester (ADR-0014, US-16): the practice repository never writes a review attempt."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from core_api.db.models import Attempt
from core_api.repositories.practice_attempt import AttemptNotFoundError, PracticeAttemptRepository
from core_api.repositories.review import AttemptRepository, ReviewSessionRepository
from practice_rows import Practice

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def test_tester_practice_save_draft_cannot_write_a_review_draft(
    practice: Practice, db_session: Session
) -> None:
    # Red when: PUT /v1/practice/attempts/{id}/draft with the id of the user's own review draft
    # changes it (the practice routes must see practice attempts only, as review routes 404 them).
    question = practice.question()
    sitting = ReviewSessionRepository(db_session, practice.user.id).start(NOW.date(), NOW)
    review = AttemptRepository(db_session, practice.user.id).create_draft(sitting.id, question.id)
    with pytest.raises(AttemptNotFoundError):
        PracticeAttemptRepository(db_session, practice.user.id).save_draft(
            review.id, answer_text="ghi đè", dont_remember=True
        )
    db_session.expire_all()
    row = db_session.get(Attempt, review.id)
    assert row is not None and (row.answer_text, row.dont_remember) == ("", False)
