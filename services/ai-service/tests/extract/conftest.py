from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text


@pytest.fixture(autouse=True)
def _no_extract_rows_left(request: pytest.FixtureRequest) -> Iterator[None]:
    """The migration test downgrades to 0002, whose CHECK refuses the task extract_session: rows
    these tests wrote must not outlive them."""
    yield
    if "engine" in request.fixturenames:
        engine: Engine = request.getfixturevalue("engine")
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM llm_call WHERE task = 'extract_session'"))
            connection.execute(text("DELETE FROM pipeline_run WHERE task = 'extract_session'"))
