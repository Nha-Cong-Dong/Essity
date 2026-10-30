from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(autouse=True)
def _no_parse_command_rows_left(request: pytest.FixtureRequest) -> Iterator[None]:
    """The migration test downgrades below 0006, whose CHECK refuses the task parse_command:
    rows these tests wrote must not outlive them."""
    yield
    if "engine" in request.fixturenames:
        engine: Engine = request.getfixturevalue("engine")
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM llm_call WHERE task = 'parse_command'"))
            connection.execute(text("DELETE FROM pipeline_run WHERE task = 'parse_command'"))


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
