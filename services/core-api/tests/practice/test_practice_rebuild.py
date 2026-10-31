"""T8.3: rebuilding practice_state from practice_log, the CLI command, and the learning-day
boundary of "due" (ADR-0029; US-06 AC7, US-16 AC7/AC11). Alice's rows only."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.cli import run
from core_api.db.models import PracticeState, User
from core_api.domain.mastery import PracticeRating
from core_api.domain.scheduling.practice import PracticeState as Domain
from core_api.domain.scheduling.practice import replay_ratings
from core_api.repositories.practice import PracticeStateRepository
from core_api.services.practice import remove
from practice_rows import Practice, day


def states(practice: Practice) -> dict[object, Domain | None]:
    repo = PracticeStateRepository(practice.session, practice.user.id)
    return {row.question_id: repo.state(row.question_id) for row in repo.list()}


def test_rebuild_all_equals_the_live_states_every_field(practice: Practice) -> None:
    # Red when: a whole-user rebuild differs from what recording the grades wrote (US-06 AC7).
    for _ in range(3):
        question = practice.question()
        for n, verdict in enumerate(["correct", "incorrect", "partial", "correct"]):
            practice.do(question, verdict, day(2 * n))  # type: ignore[arg-type]
    live = states(practice)
    repo = PracticeStateRepository(practice.session, practice.user.id)
    assert repo.rebuild() == 3
    assert states(practice) == live


def test_rebuild_keeps_removed_at_and_drops_orphan_rows(practice: Practice) -> None:
    # Red when: rebuild forgets removed_at (not in the log) or keeps a state with no log.
    kept, orphan = practice.question(), practice.question()
    practice.do(kept, "correct", day(0))
    remove(practice.session, practice.user.id, kept.id, day(1))
    practice.session.add(
        PracticeState(
            user_id=practice.user.id,
            question_id=orphan.id,
            phase="review",
            stability=1.0,
            difficulty=5.0,
            due=day(2),
            last_review=day(0),
        )
    )
    practice.session.flush()
    assert PracticeStateRepository(practice.session, practice.user.id).rebuild() == 1
    rows = practice.session.scalars(select(PracticeState)).all()
    assert [(r.question_id, r.removed_at) for r in rows] == [(kept.id, day(1))]


def test_rebuild_uses_the_latest_grade_of_each_attempt(practice: Practice) -> None:
    # Red when: an overridden grade still counts after the regrade (US-16 AC10).
    question = practice.question()
    done = practice.do(question, "correct", day(0))
    regrade = practice.grade(done.attempt, "incorrect")
    practice.record(question, regrade, "incorrect", day(0))
    state = PracticeStateRepository(practice.session, practice.user.id).state(question.id)
    assert state is not None
    assert state.last_verdict == "incorrect"
    expected = replay_ratings([(PracticeRating.AGAIN, day(0))])
    assert expected is not None
    assert state.memory == expected.memory  # one step by Again, not Good then Again


def test_rebuild_touches_only_the_users_own_rows(practice: Practice, bobs: Practice) -> None:
    # Red when: a rebuild for Alice rewrites or deletes Bob's state.
    theirs = bobs.question()
    bobs.do(theirs, "correct", day(0))
    before = states(bobs)
    practice.do(practice.question(), "correct", day(0))
    PracticeStateRepository(practice.session, practice.user.id).rebuild()
    assert states(bobs) == before


def test_cli_rebuilds_the_named_users_practice_state(
    db_session: Session,
    two_users: tuple[User, User],
    practice: Practice,
    bobs: Practice,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Red when: `rebuild-practice-state` writes nothing, or touches another user.
    mine, theirs = practice.question(), bobs.question()
    practice.do(mine, "correct", day(0))
    bobs.do(theirs, "correct", day(0))
    written, bobs_before = states(practice), states(bobs)
    db_session.query(PracticeState).filter(PracticeState.user_id == practice.user.id).delete()
    assert states(practice) == {}
    assert run(db_session, ["rebuild-practice-state", "--user-email", "alice@example.com"]) == 0
    assert states(practice) == written
    assert states(bobs) == bobs_before
    assert "1" in capsys.readouterr().out


def test_cli_unknown_email_fails_without_writing(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    # Red when: an unknown user still rebuilds something or exits 0.
    assert run(db_session, ["rebuild-practice-state", "--user-email", "nobody@example.com"]) == 1
    assert "no user" in capsys.readouterr().err


# Study-day boundary: the learning day starts at day_start_hour local time (ADR-0009, Q12).
@pytest.mark.parametrize(
    ("tz", "due_local_hour", "learning_day_end_hour", "is_due"),
    [("Asia/Ho_Chi_Minh", 3, 4, True), ("Asia/Ho_Chi_Minh", 5, 4, False)],
)
def test_due_on_respects_time_zone_and_day_start_hour(
    practice: Practice, tz: str, due_local_hour: int, learning_day_end_hour: int, is_due: bool
) -> None:
    # Red when: "due today" uses midnight or UTC instead of the user's learning day end (04:00).
    practice.user.timezone = tz
    practice.user.day_start_hour = learning_day_end_hour
    question = practice.question()
    done = practice.do(question, "correct", day(0))
    assert done.state.due is not None
    row = PracticeStateRepository(practice.session, practice.user.id).row(question.id)
    assert row is not None
    # Day 2 of Nov 2026 learning day ends at 04:00 local on Nov 3.
    row.due = datetime(2026, 11, 3, due_local_hour, 0, tzinfo=UTC) - timedelta(hours=7)
    practice.session.flush()
    due = PracticeStateRepository(practice.session, practice.user.id).due_on(date(2026, 11, 2))
    assert (question.id in {r.question_id for r in due}) is is_due


def test_due_on_exact_end_is_not_due(practice: Practice) -> None:
    # Red when: the boundary instant itself (04:00 local of the next day) counts as due today.
    practice.user.timezone = "Asia/Ho_Chi_Minh"
    practice.user.day_start_hour = 4
    question = practice.question()
    practice.do(question, "correct", day(0))
    repo = PracticeStateRepository(practice.session, practice.user.id)
    row = repo.row(question.id)
    assert row is not None
    row.due = datetime(2026, 11, 2, 21, 0, tzinfo=UTC)  # 04:00 on Nov 3 in Ho Chi Minh
    practice.session.flush()
    assert question.id not in {r.question_id for r in repo.due_on(date(2026, 11, 2))}
    row.due = datetime(2026, 11, 2, 20, 59, tzinfo=UTC)
    practice.session.flush()
    assert question.id in {r.question_id for r in repo.due_on(date(2026, 11, 2))}


def test_due_on_skips_removed_and_other_users(practice: Practice, bobs: Practice) -> None:
    # Red when: a removed question is due, or Bob's due question shows for Alice (US-16 AC11).
    gone, kept, theirs = practice.question(), practice.question(), bobs.question()
    practice.do(gone, "incorrect", day(0))
    practice.do(kept, "incorrect", day(0))
    bobs.do(theirs, "incorrect", day(0))
    remove(practice.session, practice.user.id, gone.id, day(0))
    due = PracticeStateRepository(practice.session, practice.user.id).due_on(date(2026, 12, 1))
    assert {r.question_id for r in due} == {kept.id}
