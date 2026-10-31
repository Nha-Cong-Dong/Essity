"""T7.M4, migration 0027 (PLAN T8.4, ARCH §6.2; US-16): a practice attempt belongs to no review
session. `attempt.review_session_id` is nullable, `attempt_guard` compares keys with IS DISTINCT
FROM (a plain `<>` against NULL is NULL and would let a key change through), and a review attempt
keeps its one-per-session-and-question rule."""

import uuid
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from v2_rows import World, make_question


def new_review(world: World) -> uuid.UUID:
    review = uuid.uuid4()
    world.session.execute(
        text(
            "INSERT INTO review_session (id, user_id, learning_day, started_at)"
            " VALUES (:r, :u, '2026-11-01', now())"
        ),
        {"r": review, "u": world.alice.id},
    )
    return review


def insert(
    world: World, question: uuid.UUID, review: uuid.UUID | None, status: str = "draft"
) -> uuid.UUID:
    attempt = uuid.uuid4()
    submitted = ", submitted_at" if status == "submitted" else ""
    now = ", now()" if status == "submitted" else ""
    world.session.execute(
        text(
            "INSERT INTO attempt (id, user_id, review_session_id, question_id, status"  # noqa: S608
            f"{submitted}) VALUES (:a, :u, :r, :q, :s{now})"
        ),
        {"a": attempt, "u": world.alice.id, "r": review, "q": question, "s": status},
    )
    return attempt


def update_refused(world: World, sql: str, **params: Any) -> None:
    with pytest.raises(DBAPIError, match="is refused"), world.session.begin_nested():
        world.session.execute(text(sql), params)


def test_practice_attempt_without_a_session_is_accepted(world: World) -> None:
    # Red when: attempt.review_session_id is still NOT NULL.
    question = make_question(world.session, world.alice, world.subject)
    insert(world, question.id, None)


def test_practice_attempts_at_the_same_question_may_repeat(world: World) -> None:
    # Red when: UNIQUE(review_session_id, question_id) is made to treat NULL sessions as equal
    # (a learner practises one question many times).
    question = make_question(world.session, world.alice, world.subject)
    for _ in range(3):
        insert(world, question.id, None, "submitted")


def test_review_attempt_is_still_one_per_session_and_question(world: World) -> None:
    # Red when: the unique key on a review attempt is lost.
    question = make_question(world.session, world.alice, world.subject)
    review = new_review(world)
    insert(world, question.id, review)
    with pytest.raises(IntegrityError), world.session.begin_nested():
        insert(world, question.id, review)


def test_a_session_of_another_user_is_still_refused(world: World) -> None:
    # Red when: the composite key (review_session_id, user_id) is dropped with the NOT NULL.
    question = make_question(world.session, world.alice, world.subject)
    bobs = uuid.uuid4()
    world.session.execute(
        text(
            "INSERT INTO review_session (id, user_id, learning_day, started_at)"
            " VALUES (:r, :u, '2026-11-01', now())"
        ),
        {"r": bobs, "u": world.bob.id},
    )
    with pytest.raises(IntegrityError), world.session.begin_nested():
        insert(world, question.id, bobs)


def test_a_draft_without_a_session_submits_and_is_then_frozen(world: World) -> None:
    # Red when: the guard blocks the submit UPDATE, or lets a submitted attempt change.
    question = make_question(world.session, world.alice, world.subject)
    attempt = insert(world, question.id, None)
    world.session.execute(
        text("UPDATE attempt SET status = 'submitted', submitted_at = now() WHERE id = :a"),
        {"a": attempt},
    )
    update_refused(world, "UPDATE attempt SET answer_text = 'x' WHERE id = :a", a=attempt)


def test_the_guard_refuses_a_key_change_through_null(world: World) -> None:
    # Red when: the guard uses `<>`: NULL <> x is NULL, so these changes would pass.
    question = make_question(world.session, world.alice, world.subject)
    other = make_question(world.session, world.alice, world.subject, 1)
    review = new_review(world)
    practice = insert(world, question.id, None)
    reviewed = insert(world, question.id, review)
    update_refused(
        world,
        "UPDATE attempt SET review_session_id = :r WHERE id = :a",
        r=review,
        a=practice,
    )
    update_refused(world, "UPDATE attempt SET review_session_id = NULL WHERE id = :a", a=reviewed)
    update_refused(
        world, "UPDATE attempt SET question_id = :q WHERE id = :a", q=other.id, a=practice
    )


def test_old_guard_rules_still_hold(world: World) -> None:
    # Red when: the replaced function lost a rule of 0008 (owner, id, created_at, delete).
    question = make_question(world.session, world.alice, world.subject)
    attempt = insert(world, question.id, None)
    update_refused(world, "UPDATE attempt SET id = gen_random_uuid() WHERE id = :a", a=attempt)
    update_refused(
        world, "UPDATE attempt SET user_id = :u WHERE id = :a", u=world.bob.id, a=attempt
    )
    update_refused(
        world, "UPDATE attempt SET created_at = now() - interval '1 day' WHERE id = :a", a=attempt
    )
    update_refused(world, "DELETE FROM attempt WHERE id = :a", a=attempt)


def test_downgrade_refuses_while_a_practice_attempt_exists(
    engine: Engine, alembic_cfg: Config
) -> None:
    # Red when: the downgrade sets NOT NULL over rows that have no session, or deletes them.
    # Committed on purpose (Alembic runs on its own connection); attempt rows can never be
    # deleted, so the triggers are switched off for the clean-up in `finally`.
    user, subject, question = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text('INSERT INTO "user" (id, email) VALUES (:i, :e)'),
            {"i": user, "e": f"{user}@example.com"},
        )
        c.execute(
            text("INSERT INTO subject (id, user_id, name) VALUES (:i, :u, 'M')"),
            {"i": subject, "u": user},
        )
        c.execute(
            text(
                "INSERT INTO question (id, user_id, subject_id, level, prompt, reference_answer,"
                " status, content_hash, run_id) VALUES (:i, :u, :s, 1, 'p', 'a', 'active', :h, :r)"
            ),
            {"i": question, "u": user, "s": subject, "h": "0" * 64, "r": uuid.uuid4()},
        )
        c.execute(
            text(
                "INSERT INTO attempt (id, user_id, question_id, status) VALUES"
                " (gen_random_uuid(), :u, :q, 'draft')"
            ),
            {"u": user, "q": question},
        )
    try:
        with pytest.raises(RuntimeError, match="0027 downgrade"):
            command.downgrade(alembic_cfg, "0026")
    finally:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE attempt DISABLE TRIGGER USER"))
            try:
                c.execute(text("DELETE FROM attempt WHERE user_id = :u"), {"u": user})
            finally:
                c.execute(text("ALTER TABLE attempt ENABLE TRIGGER USER"))
            c.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": user})
        command.upgrade(alembic_cfg, "head")
