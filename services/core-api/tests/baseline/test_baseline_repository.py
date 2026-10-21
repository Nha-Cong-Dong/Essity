"""T1.17: the baseline table and its repository (ADR-0001, US-11 AC2, AC5; plan B2, B5, B6, B8, B18,
B19).

The writes are single statements (`INSERT … ON CONFLICT`, `UPDATE … WHERE … RETURNING`), so each
one gets its own isolation test: Bob's call must leave Alice's row as it was.
"""

import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core_api.db.models import Baseline, User
from core_api.repositories.baseline import BaselineRepository
from core_api.repositories.user import UserRepository
from isolation import assert_isolated

NOW = datetime(2026, 10, 21, 20, 0, tzinfo=UTC)


def create(repo: BaselineRepository, gpa: str = "2.85", *, now: datetime = NOW) -> Baseline | None:
    return repo.create(
        gpa_before=Decimal(gpa),
        prior_ready_days=3,
        prior_days_unknown=False,
        is_late=False,
        now=now,
    )


def replace(repo: BaselineRepository, gpa: str, *, now: datetime) -> Baseline | None:
    return repo.replace(
        gpa_before=Decimal(gpa), prior_ready_days=5, prior_days_unknown=False, now=now
    )


def created(repo: BaselineRepository) -> Baseline:
    row = create(repo)
    assert row is not None
    return row


def test_baselines_are_isolated(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, bob = two_users
    assert_isolated(db_session, BaselineRepository, alice, bob, created)


def test_create_stores_the_values_and_entered_at(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    row = created(BaselineRepository(db_session, alice.id))
    assert (row.gpa_before, row.prior_ready_days, row.prior_days_unknown, row.is_late) == (
        Decimal("2.85"),
        3,
        False,
        False,
    )
    assert row.entered_at == NOW
    assert row.gpa_after is None


def test_plan_t1_17_second_create_returns_none_and_keeps_the_first(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    repo = BaselineRepository(db_session, alice.id)
    created(repo)
    assert create(repo, "3.50") is None
    mine = repo.get_mine()
    assert mine is not None and mine.gpa_before == Decimal("2.85")


def test_b18_bob_creating_his_own_leaves_alices_alone(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    created(BaselineRepository(db_session, alice.id))
    bobs = create(BaselineRepository(db_session, bob.id), "1.00")
    assert bobs is not None and bobs.user_id == bob.id
    alices = BaselineRepository(db_session, alice.id).get_mine()
    assert alices is not None and alices.gpa_before == Decimal("2.85")


def test_get_mine_without_a_baseline_is_none(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    created(BaselineRepository(db_session, alice.id))
    assert BaselineRepository(db_session, bob.id).get_mine() is None


def test_ac5_replace_within_seven_days_updates_and_keeps_entered_at_and_is_late(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    repo = BaselineRepository(db_session, alice.id)
    created(repo)
    row = replace(repo, "3.10", now=NOW + timedelta(days=7) - timedelta(seconds=1))
    assert row is not None
    assert (row.gpa_before, row.prior_ready_days) == (Decimal("3.10"), 5)
    assert (row.entered_at, row.is_late) == (NOW, False)


def test_ac5_replace_from_seven_days_on_returns_none_and_changes_nothing(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    repo = BaselineRepository(db_session, alice.id)
    created(repo)
    assert replace(repo, "3.10", now=NOW + timedelta(days=7)) is None
    db_session.expire_all()
    mine = repo.get_mine()
    assert mine is not None and mine.gpa_before == Decimal("2.85")


def test_replace_without_a_baseline_returns_none(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    assert replace(BaselineRepository(db_session, alice.id), "3.10", now=NOW) is None


def test_b18_bob_replacing_does_not_touch_alices_baseline(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    created(BaselineRepository(db_session, alice.id))
    assert replace(BaselineRepository(db_session, bob.id), "0.50", now=NOW) is None
    db_session.expire_all()
    alices = BaselineRepository(db_session, alice.id).get_mine()
    assert alices is not None and alices.gpa_before == Decimal("2.85")


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("gpa_before", "4.01"),
        ("gpa_before", "-0.01"),
        ("gpa_after", "4.01"),
        ("prior_ready_days", 366),
    ],
)
def test_database_refuses_values_out_of_range(
    db_session: Session, two_users: tuple[User, User], column: str, value: object
) -> None:
    alice, _ = two_users
    created(BaselineRepository(db_session, alice.id))
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(f"UPDATE baseline SET {column} = :value WHERE user_id = :user_id"),
            {"value": value, "user_id": alice.id},
        )


def test_b8_database_refuses_unknown_days_with_a_count(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    created(BaselineRepository(db_session, alice.id))
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE baseline SET prior_days_unknown = true WHERE user_id = :user_id"),
            {"user_id": alice.id},
        )


def test_database_allows_one_baseline_per_user(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    created(BaselineRepository(db_session, alice.id))
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO baseline (id, user_id, gpa_before, prior_ready_days, "
                "prior_days_unknown, entered_at, is_late) "
                "VALUES (gen_random_uuid(), :user_id, 1, 0, false, now(), false)"
            ),
            {"user_id": alice.id},
        )


# --- Skipping the prompt (AC2, B2) ------------------------------------------------------------


def test_ac2_skip_counts_up_to_two(db_session: Session, two_users: tuple[User, User]) -> None:
    alice, _ = two_users
    users = UserRepository(db_session)
    assert alice.baseline_skips == 0
    assert [users.record_baseline_skip(alice.id) for _ in range(3)] == [1, 2, 2]


def test_b18_bobs_skip_does_not_count_for_alice(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = two_users
    UserRepository(db_session).record_baseline_skip(bob.id)
    db_session.expire_all()
    assert (alice.baseline_skips, bob.baseline_skips) == (0, 1)


def test_database_refuses_more_than_two_skips(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, _ = two_users
    with pytest.raises(IntegrityError):
        db_session.execute(
            text('UPDATE "user" SET baseline_skips = 3 WHERE id = :id'), {"id": alice.id}
        )


# --- Two requests at once (B6, B19) -----------------------------------------------------------


@pytest.fixture
def committed_user(engine: Engine) -> Iterator[uuid.UUID]:
    """A user committed for real, so other connections see it; removed afterwards."""
    with Session(engine) as session:
        user = UserRepository(session).create(f"race-{uuid.uuid4().hex[:12]}@example.com")
        session.commit()
        user_id = user.id
    try:
        yield user_id
    finally:
        with Session(engine) as session:
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


def test_b19_two_creates_at_once_one_wins_the_other_gets_none(
    engine: Engine, committed_user: uuid.UUID
) -> None:
    barrier = threading.Barrier(2)
    results: list[Baseline | None] = []
    errors: list[BaseException] = []

    def attempt(gpa: str) -> None:
        try:
            with Session(engine) as session:
                barrier.wait(timeout=10)
                results.append(create(BaselineRepository(session, committed_user), gpa))
                session.commit()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=attempt, args=(gpa,)) for gpa in ("2.00", "3.00")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    assert sorted(row is None for row in results) == [False, True]
    with Session(engine) as session:
        count = session.scalar(
            select(func.count()).select_from(Baseline).where(Baseline.user_id == committed_user)
        )
    assert count == 1
