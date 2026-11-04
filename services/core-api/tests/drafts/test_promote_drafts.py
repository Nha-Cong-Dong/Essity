"""CARDS-V3: `promote-drafts` moves the draft cards that were waiting for review into the vault by
the same door a Save uses, once, without harm when run again."""

import pytest
from draft_world import RUN, World
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from clock import FROZEN_NOW
from core_api import cli
from core_api.db.models import KnowledgeUnit, Outbox, StudyLedger, UnitRevision, User
from core_api.repositories.unit import DraftRepository
from core_api.services.promote_drafts import promote_drafts
from fake_storage import FakeStorage


@pytest.fixture
def world(db_session: Session, two_users: tuple[User, User]) -> World:
    return World(db_session, two_users[0], FakeStorage())


def draft(world: World, n: int, status: str = "draft") -> KnowledgeUnit:
    repo = DraftRepository(world.db, world.user.id)
    unit_id = repo.insert_draft(
        subject_id=world.subject.id,
        session_id=world.study.id,
        draft_key=None,
        title=f"Thẻ {n}",
        summary=f"Nội dung {n}",
        kind="concept",
        section_id=world.section.id,
        run_id=RUN,
    )
    assert unit_id is not None
    repo.add_revision(unit_id, 0, "ai", {"title": f"Thẻ {n}", "content": "x", "kind": "concept"})
    unit = world.db.get(KnowledgeUnit, unit_id)
    assert unit is not None
    unit.status = status
    if status == "retired":
        unit.retired_at = FROZEN_NOW
    world.db.flush()
    return unit


def saved_events(world: World) -> int:
    rows = world.db.scalars(select(Outbox).where(Outbox.event_type == "unit.saved.v1"))
    return sum(1 for r in rows if r.payload["subject_id"] == str(world.subject.id))


def test_0038_promotes_old_drafts_not_retired(world: World) -> None:
    # Red when: a draft stays unseen, a retired card comes back, or a promoted card lacks the
    # event, revision or ledger row a Save writes.
    a, b = draft(world, 1), draft(world, 2)
    gone = draft(world, 3, "retired")
    report = promote_drafts(world.db, now=FROZEN_NOW)
    assert (report.users, report.sessions, report.cards) == (1, 1, 2)
    world.db.refresh(a)
    world.db.refresh(b)
    world.db.refresh(gone)
    assert (a.status, b.status, gone.status) == ("canonical", "canonical", "retired")
    assert a.saved_at is not None and a.saved_learning_day is not None
    assert saved_events(world) == 2
    revisions = world.db.scalars(select(UnitRevision).where(UnitRevision.unit_id == a.id)).all()
    assert sorted((r.rev, r.origin) for r in revisions) == [(0, "ai"), (1, "user")]
    ledger = world.db.scalars(select(StudyLedger).where(StudyLedger.session_id == world.study.id))
    assert sum(r.units_saved for r in ledger) == 2


def test_running_it_again_changes_nothing(world: World) -> None:
    draft(world, 1)
    promote_drafts(world.db, now=FROZEN_NOW)
    events = saved_events(world)
    again = promote_drafts(world.db, now=FROZEN_NOW)
    assert (again.sessions, again.cards) == (0, 0) and saved_events(world) == events
    revisions = world.db.scalar(select(func.count()).select_from(UnitRevision)) or 0
    assert revisions >= 2


def test_dry_run_counts_and_writes_nothing(world: World) -> None:
    unit = draft(world, 1)
    report = promote_drafts(world.db, now=FROZEN_NOW, dry_run=True)
    assert report.cards == 1
    world.db.refresh(unit)
    assert unit.status == "draft" and saved_events(world) == 0


def test_the_cli_command_runs_and_prints_the_counts(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    draft(world, 1)
    assert cli.run(world.db, ["promote-drafts", "--dry-run"]) == 0
    assert "would promote 1 cards of 1 sessions" in capsys.readouterr().out
    assert cli.run(world.db, ["promote-drafts"]) == 0
    assert "promoted 1 cards" in capsys.readouterr().out


def test_old_cards_are_saved_when_they_were_made_not_all_today(world: World) -> None:
    # Red when: every old draft is saved "now", so Hôm nay gets all of them on one day.
    from datetime import timedelta

    old, new = draft(world, 1), draft(world, 2)
    old.created_at = FROZEN_NOW - timedelta(days=5)
    new.created_at = FROZEN_NOW - timedelta(hours=1)
    world.db.flush()
    promote_drafts(world.db, now=FROZEN_NOW)
    world.db.refresh(old)
    world.db.refresh(new)
    assert old.saved_at == old.created_at and new.saved_at == new.created_at
    assert old.saved_learning_day != new.saved_learning_day
