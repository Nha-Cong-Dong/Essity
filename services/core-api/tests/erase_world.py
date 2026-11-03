"""A user with a row in every table of history, for the role tests of T2.22.

Built through the app's own repositories and commits (as `core_app`, like production): a graded
attempt with its review_log, a practice_log, a practice_removal_log, a command_log, a session item,
a draft attempt and a session that has not ended.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from core_api.domain.scheduling.rating import ReviewRating, Verdict
from core_api.repositories.question import QuestionUnitRepository
from core_api.repositories.review import (
    AttemptRepository,
    GradeRepository,
    ReviewLogRepository,
    ReviewSessionItemRepository,
    ReviewSessionRepository,
)
from core_api.repositories.user import UserRepository
from v2_rows import RUN, make_question, make_subject, make_unit

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
DONE_DAY = date(2026, 10, 29)
OPEN_DAY = date(2026, 10, 30)


@dataclass
class World:
    user_id: uuid.UUID
    grade_id: uuid.UUID
    session_id: uuid.UUID  # the one that has not ended


def build_world(engine: Engine) -> World:
    with Session(engine) as session:
        user = UserRepository(session).create(f"erase-{uuid.uuid4().hex[:12]}@example.com")
        session.flush()
        subject = make_subject(session, user)
        graded = make_question(session, user, subject, n=1)
        waiting = make_question(session, user, subject, n=2)
        unit = make_unit(session, user, subject)
        QuestionUnitRepository(session, user.id).link(graded.id, unit.id)
        sessions = ReviewSessionRepository(session, user.id)
        attempts = AttemptRepository(session, user.id)
        done = sessions.start(DONE_DAY, NOW)
        ReviewSessionItemRepository(session, user.id).add_all(done.id, [graded.id])
        attempt = attempts.create_draft(done.id, graded.id)
        attempts.save_draft(attempt.id, answer_text="x", dont_remember=False)
        attempts.submit(attempt.id, NOW)
        grade = GradeRepository(session, user.id).add_with_units(
            attempt.id,
            source="ai",
            overall=Verdict.CORRECT,
            understanding=3,
            units={unit.id: Verdict.CORRECT},
            run_id=RUN,
        )
        ReviewLogRepository(session, user.id).append(
            unit.id, rating=ReviewRating.GOOD, reviewed_at=NOW, grade_id=grade.id
        )
        sessions.end(done.id, NOW, reason="completed")
        open_session = sessions.start(OPEN_DAY, NOW)
        attempts.create_draft(open_session.id, waiting.id)
        session.flush()
        ids = {"u": user.id, "q": graded.id, "g": grade.id, "s": subject.id}
        session.execute(
            text(
                "INSERT INTO practice_log (id, user_id, question_id, rating, reviewed_at,"
                " grade_id) VALUES (gen_random_uuid(), :u, :q, 3, now(), :g)"
            ),
            ids,
        )
        session.execute(
            text(
                "INSERT INTO practice_removal_log (user_id, question_id, action)"
                " VALUES (:u, :q, 'removed')"
            ),
            ids,
        )
        session.execute(
            text(
                "INSERT INTO command_log (id, user_id, subject_id, raw_text, ops_json,"
                " inverse_json, status, affected_count, command_id, payload_hash) VALUES"
                " (gen_random_uuid(), :u, :s, 'x', '[]', '[]', 'applied', 0,"
                " gen_random_uuid(), repeat('0', 64))"
            ),
            ids,
        )
        world = World(user.id, grade.id, open_session.id)
        session.commit()
    return world


def tables_with_user_id(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.scalars(
                text(
                    "SELECT table_name FROM information_schema.columns"
                    " WHERE table_schema = 'public' AND column_name = 'user_id'"
                    " ORDER BY table_name"
                )
            )
        )


def rows_of(engine: Engine, user_id: uuid.UUID) -> dict[str, int]:
    """Row count per table that has a user_id (plus the user row itself), for this user."""
    counts: dict[str, int] = {}
    tables = tables_with_user_id(engine)
    with engine.connect() as connection:
        for table in tables:
            counts[table] = (
                connection.scalar(
                    text(f'SELECT count(*) FROM "{table}" WHERE user_id = :u'),  # noqa: S608
                    {"u": user_id},
                )
                or 0
            )
        counts["user"] = (
            connection.scalar(text('SELECT count(*) FROM "user" WHERE id = :u'), {"u": user_id})
            or 0
        )
    return counts
