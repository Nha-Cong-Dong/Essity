"""CARDS-V3, migration 0038: a study session may carry a title (at most 200 characters), a
submission may carry a notice from a closed list. Schema only: the old drafts are moved by
`promote-drafts`, not here."""

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.exc import DataError, IntegrityError

from core_api.db.models import Submission
from v2_rows import World, make_study_session


def test_single_alembic_head_after_0038(alembic_cfg: Config) -> None:
    assert len(ScriptDirectory.from_config(alembic_cfg).get_heads()) == 1


def test_a_session_title_is_stored_and_a_null_one_is_allowed(world: World) -> None:
    study = make_study_session(world.session, world.alice, world.subject)
    assert study.title is None
    study.title = "Phép thử và biến cố"
    world.session.flush()
    world.session.refresh(study)
    assert study.title == "Phép thử và biến cố"


def test_a_title_over_200_characters_is_refused(world: World) -> None:
    study = make_study_session(world.session, world.alice, world.subject)
    study.title = "x" * 201
    with pytest.raises(DataError), world.session.begin_nested():
        world.session.flush()


def _submission(world: World, notice: str | None) -> Submission:
    study = make_study_session(world.session, world.alice, world.subject)
    row = Submission(user_id=world.alice.id, session_id=study.id, status="queued", notice=notice)
    world.session.add(row)
    return row


def test_notice_in_the_list_or_null_is_accepted(world: World) -> None:
    _submission(world, "no_content_found")
    _submission(world, None)
    world.session.flush()


def test_notice_outside_the_list_is_refused(world: World) -> None:
    _submission(world, "anything the model wrote")
    with pytest.raises(IntegrityError), world.session.begin_nested():
        world.session.flush()
