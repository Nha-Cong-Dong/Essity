"""T2.23, what a skipped unit does to the choice of questions (US-06 AC6; US-04 AC5): it leaves
`TodayRepository`'s lists, schedule and history are untouched, a unit never asked counts as due,
and every unit is asked once before the exam. The session and the routes are in
test_t223_skip_session.py and test_t223_skip_api.py."""

import uuid
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_t28_today_api import RUN, Space

from clock import FROZEN_NOW
from core_api.db.models import KnowledgeUnit, MemoryState, Question, ReviewLog, User
from core_api.domain.learning_day import day_bounds, learning_day
from core_api.domain.scheduling.rating import ReviewRating
from core_api.domain.scheduling.replay import schedule_review
from core_api.domain.today import NEW_FLOOR, DueUnit, NewQuestion, compose_today
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import MemoryStateRepository
from core_api.repositories.today import TodayRepository
from core_api.repositories.unit import KnowledgeUnitRepository
from isolation import assert_isolated


def two_unit_question(space: Space, subject: uuid.UUID, prompt: str, *units: uuid.UUID) -> Question:
    question = QuestionRepository(space.session, space.user.id).add_idempotent(
        subject, level=1, prompt=prompt, reference_answer="a", run_id=RUN
    )
    for unit in units:
        QuestionUnitRepository(space.session, space.user.id).link(question.id, unit)
    space.session.flush()
    return question


def ids(rows: object) -> set[uuid.UUID]:
    return {row.question_id for row in rows}  # type: ignore[attr-defined]


def skip(space: Space, unit_id: uuid.UUID) -> None:
    assert KnowledgeUnitRepository(space.session, space.user.id).skip(unit_id, FROZEN_NOW)
    space.session.flush()


# US-06 AC6. Red when: a skipped unit's question is still offered, as due or as new.
def test_us06_ac6_a_skipped_unit_is_not_chosen_due_or_new(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    space = Space(db_session, two_users[0])
    subject = space.subject()
    due_unit, due_question = space.question(subject, "due")
    new_unit, new_question = space.question(subject, "new")
    space.scheduled(due_unit, due_in_days=-1)
    reads = TodayRepository(db_session, space.user.id)
    assert ids(reads.scheduled_units()) == {due_question.id}
    assert {q.question_id for q in reads.new_questions()} == {new_question.id}
    skip(space, due_unit)
    skip(space, new_unit)
    assert ids(reads.scheduled_units()) == set() and list(reads.new_questions()) == []


# US-06 AC6, ADR-0008. Red when: skipping writes review_log, or moves the unit's memory_state,
# or one rebuilt from review_log differs from the one before the skip.
def test_us06_ac6_skip_leaves_memory_state_and_review_log_alone(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    space = Space(db_session, two_users[0])
    unit, _ = space.question(space.subject(), "TCP")
    space.scheduled(unit, due_in_days=-1)
    states = MemoryStateRepository(db_session, space.user.id)
    before = states.state(unit)
    logs = db_session.scalar(select(func.count()).select_from(ReviewLog)) or 0
    skip(space, unit)
    assert states.state(unit) == before
    assert (db_session.scalar(select(func.count()).select_from(ReviewLog)) or 0) == logs
    assert db_session.scalar(select(func.count()).select_from(MemoryState)) == 1


# US-06 AC6. Red when: an unscheduled unit (no memory_state) is not asked: "coi như đến hạn".
def test_us06_ac6_a_unit_without_a_schedule_counts_as_due(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    space = Space(db_session, two_users[0])
    _, question = space.question(space.subject(), "TCP")
    plan = compose_today(
        TodayRepository(db_session, space.user.id).scheduled_units(),
        TodayRepository(db_session, space.user.id).new_questions(),
        {},
        now=FROZEN_NOW,
        tz=ZoneInfo(space.user.timezone),
        day_start_hour=space.user.day_start_hour,
    )
    assert [item.question_id for item in plan.items] == [question.id]


# US-06 AC6 ("hỏi đủ mảnh"). Red when: a two-unit question whose unit A was reviewed through
# another question is no longer new, so unit B is never asked.
def test_us06_ac6_a_question_with_one_unreviewed_unit_is_still_new(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    space = Space(db_session, two_users[0])
    subject = space.subject()
    unit_a, _ = space.question(subject, "A")
    unit_b, _ = space.question(subject, "B")
    both = two_unit_question(space, subject, "A và B?", unit_a, unit_b)
    space.scheduled(unit_a, due_in_days=5)
    space.scheduled(unit_b, due_in_days=5)
    reads = TodayRepository(db_session, space.user.id)
    assert both.id not in {q.question_id for q in reads.new_questions()}  # both reviewed
    MemoryStateRepository(db_session, space.user.id).delete_all()
    space.scheduled(unit_a, due_in_days=5)
    assert both.id in {q.question_id for q in reads.new_questions()}  # B never reviewed


# US-04 AC5, PLAN ("câu có mảnh bị bỏ thì ngừng chọn"). Red when: a question of two units is
# still chosen after one of them is skipped.
def test_us04_ac5_a_question_with_a_skipped_unit_is_not_chosen(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    space = Space(db_session, two_users[0])
    subject = space.subject()
    unit_a, own_a = space.question(subject, "A")
    unit_b, own_b = space.question(subject, "B")
    both = two_unit_question(space, subject, "A và B?", unit_a, unit_b)
    skip(space, unit_a)
    reads = TodayRepository(db_session, space.user.id)
    assert {q.question_id for q in reads.new_questions()} == {own_b.id}
    space.scheduled(unit_b, due_in_days=-1)
    assert ids(reads.scheduled_units()) == {own_b.id}
    assert both.id not in ids(reads.scheduled_units()) | {
        q.question_id for q in reads.new_questions()
    }
    assert own_a.id != both.id


# US-04 AC5. Red when: undo does not bring the unit back, or skipping twice / undoing without a
# skip fails instead of saying "already so".
def test_us04_ac5_skip_and_undo_are_idempotent(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    space = Space(db_session, two_users[0])
    unit, _ = space.question(space.subject(), "TCP")
    units = KnowledgeUnitRepository(db_session, space.user.id)
    assert units.unskip(unit) is False  # never skipped
    assert units.skip(unit, FROZEN_NOW) is True
    first = db_session.get(KnowledgeUnit, unit).skipped_at  # type: ignore[union-attr]
    assert units.skip(unit, FROZEN_NOW + timedelta(hours=1)) is False  # already skipped
    db_session.refresh(db_session.get(KnowledgeUnit, unit))  # type: ignore[arg-type]
    assert db_session.get(KnowledgeUnit, unit).skipped_at == first  # type: ignore[union-attr]
    assert units.unskip(unit) is True
    assert db_session.get(KnowledgeUnit, unit).skipped_at is None  # type: ignore[union-attr]
    assert len(TodayRepository(db_session, space.user.id).new_questions()) == 1


# US-04 AC5, T2.23 "cách ly". Red when: user B skips, undoes or reads user A's unit.
def test_t223_skip_is_isolated_between_users(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    space = Space(db_session, alice)
    unit, _ = space.question(space.subject(), "TCP")
    theirs = KnowledgeUnitRepository(db_session, bob.id)
    assert theirs.skip(unit, FROZEN_NOW) is False
    assert db_session.get(KnowledgeUnit, unit).skipped_at is None  # type: ignore[union-attr]
    KnowledgeUnitRepository(db_session, alice.id).skip(unit, FROZEN_NOW)
    assert theirs.unskip(unit) is False
    assert db_session.get(KnowledgeUnit, unit).skipped_at is not None  # type: ignore[union-attr]

    def create(repo: KnowledgeUnitRepository) -> KnowledgeUnit:
        return repo.create(
            space.subject("Môn khác"), title="x", summary="s", kind="concept", run_id=RUN
        )

    assert_isolated(db_session, KnowledgeUnitRepository, alice, bob, create)


# US-06 AC6, property. Red when: some unit that is not skipped is never asked before the exam,
# because of how new questions or due units are chosen. Each unit has a question of its own,
# some questions span two units, some units are skipped; a day is composed, answered right, and
# the schedule moved through `schedule_review`, as the live path does.
@given(
    units=st.integers(min_value=20, max_value=40),
    pairs=st.lists(st.tuples(st.integers(0, 29), st.integers(0, 29)), max_size=8),
    skipped=st.sets(st.integers(0, 29), max_size=6),
    days=st.integers(min_value=3, max_value=8),
    other=st.integers(min_value=0, max_value=60),
)
@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_us06_ac6_every_unit_is_asked_before_the_exam(
    db_session: Session,
    two_users: tuple[User, User],
    units: int,
    pairs: list[tuple[int, int]],
    skipped: set[int],
    days: int,
    other: int,
) -> None:
    with db_session.begin_nested() as savepoint:
        _simulate(db_session, two_users[0], units, pairs, skipped, days, other)
        savepoint.rollback()


def _simulate(
    session: Session,
    user: User,
    units: int,
    pairs: list[tuple[int, int]],
    skipped: set[int],
    days: int,
    other: int,
) -> None:
    space = Space(session, user)
    subject = space.subject(f"Môn {uuid.uuid4()}", exam_in_days=days + 1)
    unit_ids: list[uuid.UUID] = []
    for n in range(units):
        unit, _ = space.question(subject, f"mảnh {n}")
        unit_ids.append(unit)
    for n, (a, b) in enumerate(pairs):
        if a % units != b % units:
            two_unit_question(
                space, subject, f"{a}-{b}-{n}?", unit_ids[a % units], unit_ids[b % units]
            )
    # Another subject without an exam, whose questions are newer: they must not crowd the
    # exam subject's units out of the places kept for new questions (plan review O1).
    elsewhere = space.subject(f"Khác {uuid.uuid4()}")
    for n in range(other):
        space.question(elsewhere, f"khác {n}")
    gone = {unit_ids[n % units] for n in skipped}
    for unit in gone:
        skip(space, unit)
    tz = ZoneInfo(user.timezone)
    exam_day = space.today + timedelta(days=days + 1)
    asked: set[uuid.UUID] = set()
    states = MemoryStateRepository(session, user.id)
    reads = TodayRepository(session, user.id)
    for day in range(days):
        start = day_bounds(space.today + timedelta(days=day), tz, user.day_start_hour)[0]
        now = (start + timedelta(hours=8)).astimezone(UTC)
        plan = compose_today(
            reads.scheduled_units(),
            reads.new_questions(),
            {subject: exam_day},
            now=now,
            tz=tz,
            day_start_hour=user.day_start_hour,
            unasked=reads.unasked_by_subject(),
        )
        for item in plan.items:
            of_question = QuestionUnitRepository(session, user.id).units_of(item.question_id)
            for unit in of_question:
                assert unit.id not in gone, "a skipped unit was asked"
                asked.add(unit.id)
                states.upsert(
                    unit.id,
                    "core",
                    schedule_review(
                        states.state(unit.id),
                        ReviewRating.AGAIN if (day + len(asked)) % 7 == 0 else ReviewRating.GOOD,
                        now,
                        exam_day=exam_day,
                        tz=tz,
                        day_start_hour=user.day_start_hour,
                    ),
                )
        session.flush()
    assert set(unit_ids) - gone <= asked, "a unit was never asked before the exam"


@pytest.fixture(autouse=True)
def _frozen(set_now: object) -> None:  # the module's `now` is passed to compose_today directly
    return None


def _pure_plan(
    new: list[NewQuestion],
    exams: dict[uuid.UUID, object],
    unasked: dict[uuid.UUID, int] | None = None,
    *,
    due: list[DueUnit] | None = None,
    **kwargs: object,
):  # type: ignore[no-untyped-def]
    return compose_today(
        due or [],
        new,
        exams,  # type: ignore[arg-type]
        now=FROZEN_NOW,
        tz=ZoneInfo("Asia/Ho_Chi_Minh"),
        day_start_hour=4,
        unasked=unasked,
        **kwargs,  # type: ignore[arg-type]
    )


# US-06 AC6, plan review O1. Red when: the places kept for new questions go to another subject's
# newer questions, so an exam subject's older ones are never asked before the exam.
def test_us06_ac6_the_exam_subjects_old_questions_are_not_crowded_out_by_newer_ones() -> None:
    exam_subject, elsewhere = uuid.uuid4(), uuid.uuid4()
    old = FROZEN_NOW - timedelta(days=30)
    mine = [NewQuestion(uuid.uuid4(), exam_subject, old + timedelta(minutes=n)) for n in range(20)]
    theirs = [
        NewQuestion(uuid.uuid4(), elsewhere, FROZEN_NOW - timedelta(minutes=n)) for n in range(60)
    ]
    exam = learning_day(FROZEN_NOW, ZoneInfo("Asia/Ho_Chi_Minh"), 4) + timedelta(days=3)
    plan = _pure_plan([*mine, *theirs], {exam_subject: exam}, {exam_subject: 20})
    chosen = [i for i in plan.items if i.kind == "new" and i.subject_id == exam_subject]
    assert len(chosen) == 10  # ceil(20 / (3 - 1)) places, all for the exam subject


# US-06 AC6, b2. Red when: a full backlog of due units takes every place, so new questions wait
# until the due ones are gone (NEW_FLOOR places are kept).
def test_us06_ac6_a_floor_of_places_is_kept_for_new_questions_under_a_backlog() -> None:
    from core_api.domain.scheduling.fsrs_adapter import MemoryState as State
    from core_api.domain.scheduling.fsrs_adapter import Phase

    subject = uuid.uuid4()
    state = State(
        phase=Phase.REVIEW,
        step=None,
        stability=5.0,
        difficulty=5.0,
        due=FROZEN_NOW - timedelta(days=2),
        last_review=FROZEN_NOW - timedelta(days=9),
    )
    due = [DueUnit(uuid.uuid4(), subject, uuid.uuid4(), state) for _ in range(40)]
    new = [NewQuestion(uuid.uuid4(), subject, FROZEN_NOW - timedelta(minutes=n)) for n in range(9)]
    plan = _pure_plan(new, {}, due=due)
    assert len(plan.items) == 20
    assert sum(i.kind == "new" for i in plan.items) == NEW_FLOOR


# T2.23 "câu bù". Red when: the replacement ignores `exclude` (questions already in the session)
# or `room` (the places to fill), or the room is more than the day's cap.
def test_us03_ac8_a_replacement_skips_the_session_and_fills_only_the_room() -> None:
    subject = uuid.uuid4()
    new = [NewQuestion(uuid.uuid4(), subject, FROZEN_NOW - timedelta(minutes=n)) for n in range(30)]
    inside = frozenset(q.question_id for q in new[:3])
    plan = _pure_plan(new, {}, exclude=inside, room=2)
    assert len(plan.items) == 2 and not {i.question_id for i in plan.items} & inside
    assert len(_pure_plan(new, {}, room=99).items) == 20
    assert _pure_plan(new, {}, room=0).items == []
