"""T9.9, migration 0033: the trigger that turns the edges of a replaced card inactive is made by
the upgrade and removed by the downgrade, with no other change."""

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

TRIGGER = "SELECT count(*) FROM pg_trigger WHERE tgname = 'knowledge_unit_deactivate_edges'"
FUNCTION = "SELECT count(*) FROM pg_proc WHERE proname = 'knowledge_unit_deactivate_edges'"


def counts(engine: Engine) -> tuple[int, int]:
    with engine.connect() as c:
        return c.execute(text(TRIGGER)).scalar_one(), c.execute(text(FUNCTION)).scalar_one()


def test_0033_follows_0032(alembic_cfg: Config) -> None:
    # Red when: 0033 does not hang on 0032.
    assert ScriptDirectory.from_config(alembic_cfg).get_revision("0033").down_revision == "0032"


def test_0033_round_trip(engine: Engine, alembic_cfg: Config) -> None:
    # Red when: the downgrade leaves the trigger or function behind, or the upgrade omits one.
    assert counts(engine) == (1, 1)
    try:
        command.downgrade(alembic_cfg, "0032")
        assert counts(engine) == (0, 0)
    finally:
        command.upgrade(alembic_cfg, "head")
    assert counts(engine) == (1, 1)
